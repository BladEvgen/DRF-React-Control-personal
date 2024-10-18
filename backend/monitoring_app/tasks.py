import os
import cv2
import joblib
import shutil
import logging
import numpy as np
from sklearn import svm
import albumentations as A
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from monitoring_app import utils, models
from sklearn.preprocessing import StandardScaler

@shared_task
def get_all_attendance_task():
    """
    Задача Celery для выполнения функции get_all_attendance.
    """
    utils.get_all_attendance()


logger = logging.getLogger(__name__)
LOG_FILE_MAX_SIZE = 100 * 1024 * 1024
LOG_DIR = os.path.join(settings.BASE_DIR, 'logs')
error_log_file = os.path.join(LOG_DIR, 'photo_errors.log')

@shared_task
def process_lesson_attendance_batch(attendance_data, image_name, image_content):
    """
    Обрабатывает создание записей посещаемости занятий с сохранением фотографий сотрудников.

    Эта функция выполняется в асинхронной задаче через Celery и создаёт записи в базе данных
    для каждого сотрудника на основе переданных данных посещаемости. Если фотография доступна,
    она сохраняется в файловой системе.

    Args:
        attendance_data (list): Список объектов с данными о посещаемости. Каждый объект должен содержать:
            - staff_pin (str): PIN сотрудника.
            - subject_name (str): Название предмета.
            - tutor_id (int): ID преподавателя.
            - tutor (str): ФИО преподавателя.
            - first_in (str): Время начала занятия в формате ISO 8601.
            - latitude (float): Широта места проведения занятия.
            - longitude (float): Долгота места проведения занятия.
        image_name (str): Имя файла фотографии сотрудника.
        image_content (bytes): Содержимое фотографии в байтах.

    Returns:
        dict: Словарь с успешными и ошибочными записями:
            - "success_records" (list): Список ID успешно созданных записей.
            - "error_records" (list): Список ошибок с указанием PIN сотрудника и описанием ошибки.

    Raises:
        Exception: Если возникает ошибка при сохранении фотографии или создании записи в базе данных.
    """

    success_records = []
    error_records = []

    for record in attendance_data:
        try:
            staff_pin = record.get("staff_pin")
            subject_name = record.get("subject_name")
            tutor_id = record.get("tutor_id")
            tutor = record.get("tutor")
            first_in = record.get("first_in")
            latitude = record.get("latitude")
            longitude = record.get("longitude")

            staff = models.Staff.objects.get(pin=staff_pin)
            logger.info(f"Найден сотрудник с PIN: {staff_pin}")

            date_path = timezone.now().strftime("%Y-%m-%d")
            timestamp = int(timezone.now().timestamp())
            filename = f"{staff_pin}_{timestamp}.{image_name.split('.')[-1]}"

            base_path = (
                f"{settings.MEDIA_ROOT}/control_image/{staff_pin}/{date_path}"
                if settings.DEBUG
                else f"{settings.ATTENDANCE_ROOT}/{staff_pin}/{date_path}"
            )

            os.makedirs(base_path, exist_ok=True)
            logger.info(f"Создан путь: {base_path}")

            file_path = os.path.join(base_path, filename)

            try:
                with open(file_path, "wb") as destination:
                    destination.write(image_content)
                logger.info(f"Фотография успешно сохранена: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении файла: {str(e)}")
                raise

            lesson_attendance = models.LessonAttendance.objects.create(
                staff=staff,
                subject_name=subject_name,
                tutor_id=tutor_id,
                tutor=tutor,
                first_in=first_in,
                latitude=latitude,
                longitude=longitude,
                date_at=timezone.now().date(),
                staff_image_path=file_path,
            )
            logger.info(f"Запись создана с ID: {lesson_attendance.id}")

            success_records.append({"id": lesson_attendance.id})

        except models.Staff.DoesNotExist:
            error_message = f"Сотрудник с PIN {staff_pin} не найден."
            logger.error(error_message)
            error_records.append({"staff_pin": staff_pin, "error": error_message})
        except Exception as e:
            logger.error(f"Ошибка при обработке записи: {str(e)}")
            error_records.append({"staff_pin": staff_pin, "error": str(e)})

    logger.info(f"Успешные записи: {success_records}")
    logger.info(f"Ошибочные записи: {error_records}")

    return {"success_records": success_records, "error_records": error_records}


def generate_negative_samples(staff, neighbors_count=6):
    staff_list = np.array(models.Staff.objects.filter(avatar__isnull=False).order_by('pin'))

    staff_index = np.where(staff_list == staff)[0][0]

    indices = [(staff_index - i) % len(staff_list) for i in range(1, neighbors_count + 1)] + [
        (staff_index + i) % len(staff_list) for i in range(1, neighbors_count + 1)
    ]

    neighbors = staff_list[indices]

    negative_embeddings = []

    for neighbor in neighbors:
        try:
            image_path = os.path.join(settings.MEDIA_ROOT, neighbor.avatar.path)
            image = cv2.imread(image_path)
            if image is not None:
                encoding = utils.create_face_encoding(image)
                negative_embeddings.append(encoding)
        except Exception:
            logger.warning(f"Failed to create encoding for negative sample from {neighbor.pin}")

    return negative_embeddings


@shared_task
def augment_user_images(remove_old_files=False):
    augmentations = A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.RandomBrightnessContrast(p=0.5),
            A.GaussianBlur(p=0.3),
            A.Rotate(limit=40, p=0.7),
            A.ShiftScaleRotate(shift_limit=0.0625, scale_limit=0.2, rotate_limit=30, p=0.5),
            A.HueSaturationValue(p=0.5),
            A.Sharpen(p=0.3),
            A.Perspective(p=0.3),
            A.RandomResizedCrop(112, 112, scale=(0.8, 1.0), p=0.5),
        ]
    )

    staff_members = models.Staff.objects.filter(avatar__isnull=False, needs_training=True)
    success_count = 0
    error_count = 0
    error_logs = []

    for staff in staff_members:
        try:
            if not staff.avatar or not staff.avatar.name:
                raise ValueError(f"Staff {staff.pin} does not have an avatar associated with it.")

            image_path = os.path.join(settings.MEDIA_ROOT, staff.avatar.path)

            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image for {staff.pin} not found at {image_path}")

            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Failed to load image for {staff.pin}")

            output_dir = os.path.join(str(settings.AUGMENT_ROOT).format(staff_pin=staff.pin))
            os.makedirs(output_dir, exist_ok=True)

            if remove_old_files:
                logger.info(f"Removing old augmented images and model for {staff.pin}")

                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                    os.makedirs(output_dir, exist_ok=True)

                model_path = os.path.join(
                    os.path.dirname(staff.avatar.path), f'{staff.pin}_model.pkl'
                )
                if os.path.exists(model_path):
                    os.remove(model_path)
                    logger.info(f"Removed old model file for {staff.pin}: {model_path}")

            augmented_images = []
            for i in range(10):
                augmented_image = augmentations(image=image)["image"]
                augmented_images.append(augmented_image)

            for i, aug_image in enumerate(augmented_images):
                augmented_filename = f'{staff.pin}_augmented_{i}.jpg'
                augmented_path = os.path.join(output_dir, augmented_filename)
                cv2.imwrite(augmented_path, aug_image)

            embeddings = [utils.create_face_encoding(image) for image in augmented_images]

            negative_embeddings = generate_negative_samples(staff)

            utils.train_face_recognition_model(staff, embeddings, negative_embeddings)

            staff.needs_training = False
            staff.save()
            success_count += 1
        except Exception as e:
            error_logs.append(f"Error for {staff.pin}: {str(e)}")
            logger.error(f"Error for {staff.pin}: {str(e)}")
            log_photo_error(f"Error for {staff.pin}: {str(e)}")
            error_count += 1

    return {
        "status": "Completed",
        "successful_augmentations": success_count,
        "failed_augmentations": error_count,
        "error_log": error_logs,
    }


def initialize_log_file():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    if os.path.exists(error_log_file) and os.path.getsize(error_log_file) > LOG_FILE_MAX_SIZE:
        os.remove(error_log_file)

    with open(error_log_file, "a") as log_file:
        log_file.write(f"========== Лог начат {timezone.localtime(timezone.now())} ==========\n")


def log_photo_error(message):
    initialize_log_file()
    current_time = timezone.localtime(timezone.now())
    with open(error_log_file, "a") as log_file:
        log_file.write(f"{current_time}: {message}\n")
    logger.warning(message)
