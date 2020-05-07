"""web_survey URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from app_user import views as user_views
from app_survey import views as survey_views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("account/login-signup/", user_views.vw_login_register),
    path("account/change-password/", user_views.vw_change_password),
    path("account/logout/", auth_views.LogoutView.as_view(), name="user_logout"),
    path("", survey_views.vw_intro, name="home"),
    path("survey/step1/", survey_views.vw_step1, name="step1"),
    path("survey/step2/", survey_views.vw_step2, name="step2"),
    path("survey/step3/", survey_views.vw_step3, name="step3"),
    path("survey/step4/", survey_views.vw_step4, name="step4"),
    path("survey/step5/", survey_views.vw_step5, name="step5"),
    path("survey/step5/save_suggestions", survey_views.saveSuggestions, name="saveSuggestions"),
    path("survey/step5/save_demographic_infos", survey_views.saveDemographicInfos, name="saveDemographicInfos"),
    path("survey/export_csv", survey_views.exportCSV, name="exportCSV"),
    path("survey/finish0/", survey_views.vw_finish0),
    path("survey/purpose_detail/<int:purpose_id>/", survey_views.get_purpose_detail),
    path("move/<str:dir>/<int:pos>", survey_views.vw_move)
]
