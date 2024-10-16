from django.urls import path, re_path
from rest_framework_simplejwt.views import (
    TokenVerifyView,
    TokenRefreshView,
)

from monitoring_app import views, custom_jwt
from django.views.generic import RedirectView
from monitoring_app.swagger import urlpatterns as doc_urls

urlpatterns = [
    path("", RedirectView.as_view(url="/app/")),
    path("login_view/", views.login_view, name="login_view"),
    path("logout/", views.logout_view, name="logout"),
    path("upload/", views.UploadFileView.as_view(), name="uploadFile"),
    path("fetcher/", views.fetch_data_view, name="fetcher"),
    path(
        "api/attendance/stats/",
        views.StaffAttendanceStatsView.as_view(),
        name="staff-attendance-stats",
    ),
    path("api/locations", views.map_location, name="locations"),
    path("api/lesson_attendance/", views.create_lesson_attendance, name="create_lesson_attendance"),
    path(
        "api/lesson_attendance/<int:id>/",
        views.update_lesson_attendance,
        name="update_lesson_attendance",
    ),
    path(
        "api/lesson_attendance/task_status/<str:task_id>/",
        views.check_lesson_task_status,
        name="check_lesson_task_status",
    ),
    path(
        "api/child_department/<str:child_department_id>/",
        views.child_department_detail,
        name="child-department-detail",
    ),
    path(
        "api/department/stats/<str:department_id>/",
        views.staff_detail_by_department_id,
        name="department-stats",
    ),
    path(
        "api/department/<str:parent_department_id>/",
        views.department_summary,
        name="department-summary",
    ),
    path("api/download/<str:department_id>/", views.sent_excel, name="sent_excel"),
    path("api/key_check/", views.APIKeyCheckView.as_view(), name="api_key_check"),
    path("api/parent_department_id/", views.get_parent_id, name="get-parent-ids"),
    path("api/staff/<str:staff_pin>/", views.staff_detail, name="staff-detail"),
    path(
        "api/token/",
        custom_jwt.CustomTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    path("api/token/verify/", TokenVerifyView.as_view()),
    path("api/user/detail/", views.user_profile_detail, name="user-detail"),
    path("api/user/register/", views.user_register, name="userRegister"),
    path(
        "password-reset/",
        views.password_reset_request_view,
        name="password_reset_request",
    ),
    path(
        "password-reset/<str:token>/",
        views.password_reset_confirm_view,
        name="password_reset_confirm",
    ),
    path('verify-face/', views.verify_face, name='verify-face'),
    path("recognize-faces/", views.recognize_faces, name="recognize-faces"),
]

urlpatterns += doc_urls

urlpatterns += [
    re_path(r"^app/.*$", views.react_app, name="reac_app"),
]
