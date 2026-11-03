from django.urls import path, register_converter

from . import views


class InkIdConverter:
    regex = "[A-Za-z0-9_-]{1,64}"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return value


register_converter(InkIdConverter, "inkid")

_api = "api/ink/v1/notebooks/<inkid:notebook_id>"
_page = f"{_api}/pages/<inkid:page_id>"

urlpatterns = [
    path("sw.js", views.service_worker, name="service_worker"),
    path("notebook/", views.new_notebook, name="new_notebook"),
    path("notebook/<inkid:notebook_id>/", views.notebook, name="notebook"),
    path(f"{_api}/", views.notebook_snapshot, name="notebook_snapshot"),
    path(f"{_api}/document/ops/", views.document_ops, name="document_ops"),
    path(f"{_page}/ops/", views.page_ops, name="page_ops"),
    path(f"{_page}/reconstruction/", views.reconstruction, name="reconstruction"),
    path(f"{_page}/render.png", views.render_page, name="render_page"),
    path(f"{_page}/revisions/", views.revisions, name="revisions"),
]
