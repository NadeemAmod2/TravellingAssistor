from django.contrib import admin
from app_survey.models import mdl_travel,mdl_flexibility, \
                            mdl_purpose, mdl_purpose_detail
# Register your models here.
admin.site.register(mdl_travel)
admin.site.register(mdl_flexibility)
admin.site.register(mdl_purpose)
admin.site.register(mdl_purpose_detail)


