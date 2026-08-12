from django.conf import settings


def branding(request):
    return {
        "KUSANYA_BRAND_NAME": settings.KUSANYA_BRAND_NAME,
        "KUSANYA_TAGLINE": settings.KUSANYA_TAGLINE,
    }
