"""Public website. It describes the project and holds no business rules."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    # The prototype has no authentication, so it is only linked where its routes exist.
    return render(request, "pages/home.html", {"notebook_enabled": settings.INK_PROTOTYPE_ENABLED})
