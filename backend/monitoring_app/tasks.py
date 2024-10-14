import os
import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from monitoring_app import utils, models


@shared_task
def get_all_attendance_task():
    """
    Задача Celery для выполнения функции get_all_attendance.
    """
    utils.get_all_attendance()


logger = logging.getLogger(__name__)


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
