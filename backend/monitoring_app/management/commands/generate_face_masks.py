from django.core.management.base import BaseCommand
from monitoring_app.tasks import augment_user_images
from monitoring_app.utils import create_face_encoding
from django.core.exceptions import ObjectDoesNotExist
from monitoring_app.models import Staff, StaffFaceMask


class Command(BaseCommand):
    help = 'Создать маски для всех сотрудников и запустить обучение модели'

    def handle(self, *args, **kwargs):
        staffs = Staff.objects.filter(avatar__isnull=False)
        total_created = 0
        total_updated = 0

        for staff in staffs:
            try:
                avatar_path = staff.avatar.path
                encoding = create_face_encoding(avatar_path)

                face_mask, created = StaffFaceMask.objects.update_or_create(
                    staff=staff, defaults={"mask_encoding": encoding}
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(f'Маска создана для {staff.pin}'))
                    total_created += 1
                else:
                    self.stdout.write(self.style.SUCCESS(f'Маска обновлена для {staff.pin}'))
                    total_updated += 1

            except ObjectDoesNotExist:
                self.stderr.write(self.style.ERROR(f'Не удалось найти аватар для {staff.pin}'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Ошибка для {staff.pin}: {str(e)}'))

        if total_created > 0 or total_updated > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Создано {total_created} масок, обновлено {total_updated}. Запуск обучения модели...'
                )
            )
            augment_user_images.delay()
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Маски не были созданы или обновлены, обучение модели не запущено.'
                )
            )
