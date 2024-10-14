import os
import shutil

from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.dispatch import receiver
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.validators import FileExtensionValidator
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save

from monitoring_app import utils
from django_admin_geomap import GeoItem


class PasswordResetTokenManager(models.Manager):
    def mark_as_used(self, token):
        token_obj = self.filter(token=token, _used=False).first()
        if token_obj and token_obj.is_valid():
            token_obj._used = True
            token_obj.save(update_fields=["_used"])
            return True
        return False


class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    token = models.CharField(max_length=64, unique=True, verbose_name="Токен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    _used = models.BooleanField(default=False, verbose_name="Статус использования")

    objects = PasswordResetTokenManager()

    @property
    def used(self):
        return self._used

    def is_valid(self):
        expiration_time = timezone.now() - timezone.timedelta(hours=1)
        return self.created_at > expiration_time and not self._used

    @staticmethod
    def generate_token(user):
        token = get_random_string(64)
        PasswordResetToken.objects.create(user=user, token=token)
        return token

    def save(self, *args, **kwargs):
        if self.pk:
            original = PasswordResetToken.objects.get(pk=self.pk)
            if original.token != self.token:
                self.token = original.token
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Токен для сброса пароля"
        verbose_name_plural = "Токены для сброса паролей"


class PasswordResetRequestLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    ip_address = models.GenericIPAddressField(verbose_name="IP-адрес")
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="Время запроса")

    @staticmethod
    def is_recent_request(user, ip_address):
        five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
        return PasswordResetRequestLog.objects.filter(
            user=user, ip_address=ip_address, requested_at__gte=five_minutes_ago
        ).exists()

    @staticmethod
    def get_last_request_time(user, ip_address):
        last_request = (
            PasswordResetRequestLog.objects.filter(user=user, ip_address=ip_address)
            .order_by("-requested_at")
            .first()
        )
        return last_request.requested_at if last_request else None

    @staticmethod
    def log_request(user, ip_address):
        PasswordResetRequestLog.objects.create(user=user, ip_address=ip_address)

    @staticmethod
    def can_request_again(user, ip_address):
        last_request_time = PasswordResetRequestLog.get_last_request_time(user, ip_address)
        if not last_request_time:
            return True
        return timezone.now() >= last_request_time + timezone.timedelta(minutes=5)

    class Meta:
        verbose_name = "Лог запросов на сброс пароля"
        verbose_name_plural = "Логи запросов на сброс пароля"


class APIKey(models.Model):
    key_name = models.CharField(
        max_length=100, null=False, blank=False, verbose_name="Название ключа"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, verbose_name="Создатель"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    key = models.CharField(max_length=256, editable=False, verbose_name="Ключ")
    is_active = models.BooleanField(default=True, editable=True, verbose_name="Статус активности")

    def __str__(self):
        status = "Активен" if self.is_active else "Деактивирован"

        return f"Ключ: {self.key_name}  Статус активности: {status}"

    def save(self, *args, **kwargs):
        if not self.key:
            encrypted_key, secret_key = utils.APIKeyUtility.generate_api_key(
                self.key_name, self.created_by
            )
            self.key = encrypted_key
        super(APIKey, self).save(*args, **kwargs)

    class Meta:
        verbose_name = "API Ключ"
        verbose_name_plural = "API Ключи"


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Пользователь",
    )
    is_banned = models.BooleanField(default=False, verbose_name="Статус Блокировки")
    phonenumber = models.CharField(max_length=20, verbose_name="Номер телефона")
    last_login_ip = models.GenericIPAddressField(
        verbose_name="Последний IP-адрес входа", null=True, blank=True
    )

    def __str__(self):
        return f"{self.user.username} Profile"

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=UserProfile)
def update_user_active_status(sender, instance, **kwargs):
    if instance.is_banned:
        instance.user.is_active = False
    else:
        instance.user.is_active = True
    instance.user.save()


@receiver(post_delete, sender=UserProfile)
def delete_user_on_profile_delete(sender, instance, **kwargs):
    user = instance.user
    user.delete()


@receiver(post_save, sender=UserProfile)
@receiver(post_delete, sender=UserProfile)
def update_jwt_token(sender, instance, **kwargs):
    user = instance.user
    RefreshToken.for_user(user)


class FileCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название шаблона")
    slug = models.SlugField(unique=True, verbose_name="Ссылка")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Категория файла"
        verbose_name_plural = "Категории файлов"


class ParentDepartment(models.Model):
    id = models.CharField(primary_key=True, verbose_name="Номер отдела", max_length=10)
    name = models.CharField(max_length=255, unique=True, verbose_name="Название отдела")
    date_of_creation = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return self.name

    @classmethod
    def len_parent_departments(cls) -> int:
        return cls.objects.count()

    class Meta:
        verbose_name = "Родительский отдел"
        verbose_name_plural = "Родительские отделы"


class ChildDepartment(models.Model):
    id = models.CharField(primary_key=True, verbose_name="Номер отдела", max_length=10)
    name = models.CharField(max_length=255, verbose_name="Название отдела")
    date_of_creation = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Родительский отдел",
    )

    def __str__(self):
        return self.name

    @classmethod
    def len_child_departments(cls) -> int:
        return cls.objects.count()

    def save(self, *args, **kwargs):
        if not self.id:
            existing_child_department = ChildDepartment.objects.filter(name=self.name).first()
            if existing_child_department:
                self.id = existing_child_department.id
                self.parent = existing_child_department.parent

        super().save(*args, **kwargs)

    def get_all_child_departments(self):
        children = self.children.all()
        all_children = list(children)
        for child in children:
            all_children.extend(child.get_all_child_departments())
        return all_children

    class Meta:
        verbose_name = "Подотдел"
        verbose_name_plural = "Подотделы"


class Position(models.Model):
    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        verbose_name="Профессия",
        default="Сотрудник",
    )
    rate = models.DecimalField(max_digits=4, decimal_places=2, verbose_name="Ставка", default=1)

    def __str__(self):
        return f"{self.name} Ставка: {self.rate}"

    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"


def user_avatar_path(instance, filename):
    return f"user_images/{instance.pin}/{instance.pin}.{filename.split('.')[-1]}"


class Staff(models.Model):
    pin = models.CharField(
        max_length=100,
        blank=False,
        null=False,
        unique=True,
        verbose_name="Id сотрудника",
        editable=False,
    )
    name = models.CharField(max_length=255, blank=False, null=False, verbose_name="Имя")
    surname = models.CharField(max_length=255, blank=False, null=False, verbose_name="Фамилия")
    department = models.ForeignKey(
        ChildDepartment, on_delete=models.SET_NULL, null=True, verbose_name="Отдел"
    )
    date_of_creation = models.DateTimeField(
        default=timezone.now, editable=False, verbose_name="Дата добавления"
    )

    positions = models.ManyToManyField(Position, verbose_name="Должность")
    avatar = models.ImageField(
        upload_to=user_avatar_path,
        null=True,
        blank=True,
        verbose_name="Фото Пользователя",
        validators=[FileExtensionValidator(allowed_extensions=["jpg"])],
    )

    def __str__(self):
        return f"{self.surname} {self.name}"

    def save(self, *args, **kwargs):
        if self.pk:
            old_avatar = Staff.objects.filter(pk=self.pk).values("avatar").first()
            if old_avatar and old_avatar["avatar"] != self.avatar and self.avatar:
                try:
                    old_avatar_path = old_avatar["avatar"]
                    if os.path.exists(old_avatar_path):
                        os.remove(old_avatar_path)
                except Exception as e:
                    print(f"Ошибка при удалении старой аватарки: {e}")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        avatar_dir = os.path.dirname(self.avatar.path)
        if os.path.exists(avatar_dir):
            try:
                shutil.rmtree(avatar_dir)
            except Exception as e:
                print(f"Ошибка при удалении директории с аватаркой: {e}")
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"


@receiver(post_delete, sender=Staff)
def delete_avatar_on_staff_delete(sender, instance, **kwargs):
    if instance.avatar:
        avatar_dir = os.path.dirname(instance.avatar.path)
        if os.path.exists(avatar_dir):
            try:
                shutil.rmtree(avatar_dir)
            except Exception as e:
                print(f"Ошибка при удалении директории с аватаркой после удаления сотрудника: {e}")
    else:
        print("Аватар отсутствует, ничего не удаляется.")


class AbsentReason(models.Model):
    ABSENT_REASON_CHOICES = [
        ("business_trip", "Командировка"),
        ("sick_leave", "Болезнь"),
        ("other", "Другая причина"),
    ]

    staff = models.ForeignKey(
        Staff, on_delete=models.CASCADE, related_name="absences", verbose_name="Сотрудник"
    )
    reason = models.CharField(
        max_length=20, choices=ABSENT_REASON_CHOICES, verbose_name="Причина отсутствия"
    )
    start_date = models.DateField(verbose_name="Дата начала")
    end_date = models.DateField(verbose_name="Дата окончания")
    approved = models.BooleanField(default=False, verbose_name="Утверждено")
    document = models.FileField(
        upload_to="absence_documents/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
        verbose_name="Документ",
    )

    def save(self, *args, **kwargs):
        if self.reason == "business_trip":
            self.approved = True
        elif self.reason == "sick_leave" and self.document:
            self.approved = True

        if self.document:
            self.document.name = utils.transliterate(self.document.name)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff} - {self.get_reason_display()} ({self.start_date} - {self.end_date})"

    class Meta:
        verbose_name = "Уважительная причина отсутствия"
        verbose_name_plural = "Уважительные причины отсутствия"


class RemoteWork(models.Model):
    staff = models.ForeignKey(
        Staff, on_delete=models.CASCADE, related_name="remote_work", verbose_name="Сотрудник"
    )
    start_date = models.DateField(verbose_name="Дата начала", null=True, blank=True)
    end_date = models.DateField(verbose_name="Дата окончания", null=True, blank=True)
    permanent_remote = models.BooleanField(
        default=False, verbose_name="Постоянная дистанционная работа"
    )

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("Дата начала не может быть больше даты окончания.")
        if self.permanent_remote and (self.start_date or self.end_date):
            raise ValidationError("Постоянная дистанционная работа не требует указания дат.")

    def __str__(self):
        return f"{self.staff} - {self.get_remote_status()}"

    def get_remote_status(self):
        return (
            "Постоянная дистанционная работа"
            if self.permanent_remote
            else f"Дистанционная работа ({self.start_date} - {self.end_date})"
        )

    class Meta:
        verbose_name = "Дистанционная работа"
        verbose_name_plural = "Дистанционная работа"


class StaffAttendance(models.Model):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="attendance",
        verbose_name="Сотрудник",
        editable=False,
    )
    date_at = models.DateField(
        verbose_name="Дата добавления записи в Таблицу",
        editable=False,
    )
    first_in = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время первого входа",
        editable=True,
        default=None,
    )
    last_out = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время последнего выхода",
        editable=True,
        default=None,
    )

    absence_reason = models.ForeignKey(
        AbsentReason,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="Причина отсутствия",
    )

    area_name_in = models.CharField(
        null=True, blank=True, max_length=300, verbose_name="Зона входа"
    )
    area_name_out = models.CharField(
        null=True, blank=True, max_length=300, verbose_name="Зона выхода"
    )

    def __str__(self) -> str:
        return f"{self.staff} {self.date_at.strftime('%d-%m-%Y')}"

    def save(self, *args, **kwargs):
        if "force_insert" in kwargs:
            kwargs.pop("force_insert")

        if self.pk and not self._state.adding:
            orig = StaffAttendance.objects.get(pk=self.pk)
            if (
                self.first_in != orig.first_in or self.last_out != orig.last_out
            ) and "admin" in kwargs:
                raise ValidationError("Нельзя изменять поля first_in и last_out через админку.")

        super().save(*args, **kwargs)

    class Meta:
        unique_together = [["staff", "date_at"]]

        verbose_name = "Посещаемость сотрудника"
        verbose_name_plural = "Посещаемость сотрудников"


class LessonAttendance(models.Model, GeoItem):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="lesson_attendance",
        verbose_name="Сотрудник",
        editable=False,
    )
    subject_name = models.CharField(
        verbose_name="Название предмета", max_length=300, editable=False
    )
    tutor_id = models.IntegerField(verbose_name="Id преподавателя", editable=False)
    tutor = models.CharField(verbose_name="ФИО преподавателя", max_length=300)
    first_in = models.DateTimeField(verbose_name="Время начала занятия", null=False)
    last_out = models.DateTimeField(verbose_name="Время окончания занятия", null=True, blank=True)
    latitude = models.FloatField(
        verbose_name="Широта", editable=False, help_text="Примерные координаты в радиусе 300 метров"
    )
    longitude = models.FloatField(
        verbose_name="Долгота",
        editable=False,
        help_text="Примерные координаты в радиусе 300 метров",
    )
    date_at = models.DateField(verbose_name="Дата занятия", default=timezone.now)
    staff_image_path = models.CharField(
        max_length=500,
        verbose_name="Путь к фотографии сотрудника",
        null=True,
        blank=True,
    )

    @property
    def image_url(self):
        if self.staff_image_path:
            if self.staff_image_path.startswith(settings.ATTENDANCE_ROOT):
                relative_path = self.staff_image_path.replace(settings.ATTENDANCE_ROOT, "")
                return f"{settings.ATTENDANCE_URL}{relative_path}"
            return f"{settings.MEDIA_URL}{self.staff_image_path.split('media/')[-1]}"
        return "/static/media/images/no-avatar.png"

    def is_photo_expired(self):
        return (timezone.now().date() - self.date_at).days > 31

    @property
    def geomap_longitude(self):
        return str(self.longitude)

    @property
    def geomap_latitude(self):
        return str(self.latitude)

    @property
    def formatted_first_in(self):
        return self.first_in.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def formatted_last_out(self):
        if self.last_out:
            return self.last_out.strftime("%Y-%m-%d %H:%M:%S")
        return "Ongoing"

    @property
    def tutor_info(self):
        return f"{self.tutor} (ID: {self.tutor_id})"

    def __str__(self):
        return f"{self.subject_name} ({self.staff}) [{self.date_at}]"

    class Meta:
        verbose_name = "Посещаемость занятия"
        verbose_name_plural = "Посещаемость занятий"


class Salary(models.Model):
    CONTRACT_TYPE_CHOICES = [
        ("full_time", "Полная занятость"),
        ("part_time", "Частичная занятость"),
        ("gph", "ГПХ"),
    ]
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="salaries",
        verbose_name="Сотрудник",
    )

    net_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=False,
        null=False,
        verbose_name="Чистая зарплата",
    )
    total_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        editable=False,
        verbose_name="Итоговая зарплата",
    )
    contract_type = models.CharField(
        max_length=20,
        choices=CONTRACT_TYPE_CHOICES,
        default="full_time",
        verbose_name="Тип контракта",
    )

    class Meta:
        verbose_name = "Зарплата"
        verbose_name_plural = "Зарплаты"

    def clean(self):
        total_rate = sum(self.staff.positions.values_list("rate", flat=True))
        if total_rate > 1.5:
            raise ValidationError(
                "Суммарная ставка не может превышать 1.5. Пожалуйста, измените ставки должностей."
            )

    @staticmethod
    def calculate_total_salary(net_salary, rate):
        return net_salary * rate

    def calculate_salaries(self):
        self.clean()
        total_rate = sum(self.staff.positions.values_list("rate", flat=True))
        self.total_salary = self.calculate_total_salary(self.net_salary, total_rate)

    def save(self, *args, **kwargs):
        try:
            with transaction.atomic():
                self.calculate_salaries()
                super().save(*args, **kwargs)
        except ValidationError:
            if hasattr(self, "_request"):
                messages.error(
                    self._request,
                    "Суммарная ставка не может превышать 1.5. Изменения не сохранены.",
                )
            previous_instance = Salary.objects.get(pk=self.pk)
            self.total_salary = previous_instance.total_salary


@receiver(pre_save, sender=Salary)
def calculate_salaries(sender, instance, **kwargs):
    instance.calculate_salaries()


@receiver(m2m_changed, sender=Staff.positions.through)
def update_salary_on_position_change(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        for salary in instance.salaries.all():
            try:
                with transaction.atomic():
                    salary.calculate_salaries()
                    salary.save(update_fields=["total_salary"])
            except ValidationError:
                if hasattr(salary, "_request"):
                    messages.error(
                        salary._request,
                        "Суммарная ставка не может превышать 1.5. Изменения не сохранены.",
                    )
                previous_instance = Salary.objects.get(pk=salary.pk)
                salary.total_salary = previous_instance.total_salary


class PublicHoliday(models.Model):
    date = models.DateField(unique=True, verbose_name="Дата праздника")
    name = models.CharField(max_length=255, verbose_name="Название праздника")
    is_working_day = models.BooleanField(default=False, verbose_name="Рабочий день")

    def __str__(self):
        return f"{self.name} ({self.date})"

    class Meta:
        verbose_name = "Праздничный день"
        verbose_name_plural = "Праздничные дни"
