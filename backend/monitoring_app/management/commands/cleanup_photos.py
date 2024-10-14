import os
from django.utils import timezone
from monitoring_app.models import LessonAttendance
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Удаляет фотографии старше 31 дня"

    def handle(self, *args, **kwargs):
        cutoff_date = timezone.now().date() - timezone.timedelta(days=31)
        records = LessonAttendance.objects.filter(date_at__lt=cutoff_date)

        for record in records:
            if record.staff_image_path and os.path.exists(record.staff_image_path):
                os.remove(record.staff_image_path)
                self.stdout.write(f"Удалена фотография: {record.staff_image_path}")
            else:
                self.stdout.write(
                    f"Фотография уже удалена или не найдена: {record.staff_image_path}"
                )
