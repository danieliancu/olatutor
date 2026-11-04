from django.urls import path

from apps.notebooks import urls as _notebook_urls  # noqa: F401  Registers the `inkid` converter.

from . import views

_page = "api/grading/v1/notebooks/<inkid:notebook_id>/pages/<inkid:page_id>"

urlpatterns = [
    path("api/grading/v1/exercises/", views.exercises, name="grading_exercises"),
    path(f"{_page}/verifications/", views.verifications, name="grading_verifications"),
    path(
        f"{_page}/verifications/<int:verification_id>/explanation/",
        views.explanation,
        name="grading_explanation",
    ),
]
