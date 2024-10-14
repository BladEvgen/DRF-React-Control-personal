import os
import time
import pytz
import json
import aiohttp
import asyncio
from datetime import datetime

base_url = "http://localhost:8000/api/"
create_lesson_url = f"{base_url}lesson_attendance/"
check_task_url = f"{base_url}lesson_attendance/task_status/"
update_lesson_url = f"{base_url}lesson_attendance/"
api_token = "TOKEN"

headers = {
    "X-API-KEY": api_token,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logs_dir = os.path.join(BASE_DIR, "logs")

if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

log_file_path = os.path.join(logs_dir, "lesson_attendance_test.log")


def log_message(message):
    with open(log_file_path, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    print(message)


def generate_random_data(staff_pin):
    tz = pytz.timezone("Asia/Almaty")
    current_time = datetime.now(tz).isoformat()
    latitude = 43.207674
    longitude = 76.851377
    return {
        "staff_pin": staff_pin,
        "subject_name": "Медицина",
        "tutor_id": 861,
        "tutor": "Вдовцев Александр Викторович",
        "first_in": current_time,
        "latitude": latitude,
        "longitude": longitude,
    }


async def create_lesson_attendance(session, staff_pin):
    data = generate_random_data(staff_pin)
    image_path = "/path/to/picture.extension"

    form_data = aiohttp.FormData()

    form_data.add_field(
        "attendance_data",
        json.dumps([data]),
        content_type="application/json",
    )
    form_data.add_field("image", open(image_path, "rb"), filename=os.path.basename(image_path))

    async with session.post(create_lesson_url, headers=headers, data=form_data) as response:
        if response.status == 202:
            result = await response.json()
            task_id = result.get("task_id")
            log_message(f"Сотрудник {staff_pin}: Task создан, task_id: {task_id}")
            return task_id
        else:
            log_message(
                f"Ошибка создания записи для {staff_pin}: {response.status} - {await response.text()}"
            )
            return None


async def check_task_status(session, task_id, max_retries=5, wait_time=5):
    retries = 0
    while retries < max_retries:
        async with session.get(f"{check_task_url}{task_id}/", headers=headers) as response:
            if response.status == 200:
                result = await response.json()
                status = result.get("status")
                log_message(f"Статус задачи {task_id}: {status}")
                if status == "Success":
                    lesson_records = result.get("lesson_ids", [])
                    if lesson_records:
                        lesson_id = lesson_records[0].get("id")
                        log_message(f"Успешно завершенные записи: {lesson_id}")
                        return lesson_id
                elif status == "Pending":
                    log_message(f"Задача {task_id} еще в очереди")
                else:
                    log_message(f"Задача {task_id} еще не завершена")
            else:
                log_message(
                    f"Ошибка проверки статуса задачи {task_id}: {response.status} - {await response.text()}"
                )

        retries += 1
        await asyncio.sleep(wait_time)

    log_message(f"Задача {task_id} не завершена после {max_retries} попыток.")
    return None


async def update_lesson_attendance(session, lesson_id):
    random_last_out = time.strftime("%Y-%m-%dT%H:%M:%S")
    data = {"last_out": random_last_out}

    async with session.put(
        f"{update_lesson_url}{lesson_id}/", headers=headers, json=data
    ) as response:
        if response.status == 200:
            log_message(f"Запись с ID {lesson_id} успешно обновлена.")
        else:
            log_message(
                f"Ошибка обновления записи {lesson_id}: {response.status} - {await response.text()}"
            )


async def process_lesson_attendance(staff_pin, session):
    task_id = await create_lesson_attendance(session, staff_pin)

    if task_id:
        lesson_id = await check_task_status(session, task_id)

        if lesson_id:
            await update_lesson_attendance(session, lesson_id)


async def run_tests():
    staff_members = [
        "s7677",
        "s756790",
        "s22311",
        "s100323",
        "s00375",
        "s00260",
        "s00226",
        "s00173",
        "s00105",
        "s00018",
        "S15213213231132",
    ]

    async with aiohttp.ClientSession() as session:
        tasks = [process_lesson_attendance(staff_pin, session) for staff_pin in staff_members]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(run_tests())
