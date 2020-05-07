from django import forms
from app_survey.models import mdl_travel,mdl_flexibility,mdl_purpose,mdl_purpose_detail

class frm_travel(forms.ModelForm):
    departure_time = forms.TimeField(widget=forms.TimeInput(format='%H:%M'))
    arrival_time = forms.TimeField(widget=forms.TimeInput(format='%H:%M'))
    flexibles = forms.ModelMultipleChoiceField(queryset=mdl_flexibility.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)
    last_activity=forms.BooleanField(initial=False, required=False,widget=forms.CheckboxInput(attrs={'class': 'checkbox'})) 
    purpose=forms.ModelChoiceField(queryset=mdl_purpose.objects.all(), required=True)
    class Meta:
        model=mdl_travel
        exclude=("user","session","position","type")
        
    def __init__(self, *args, **kwargs):
        self.purpose = kwargs.pop('purpose', None)
        self.purpose_detail = kwargs.pop('purpose_detail', None)
        super(frm_travel, self).__init__(*args, **kwargs)
        self.fields['purpose_detail'].queryset = mdl_purpose_detail.objects.filter(purpose__id=self.purpose if self.purpose else 0 )
        if self.purpose_detail:
            self.fields['purpose_detail'].initial = self.purpose_detail
            
    def clean_travel_from_longitude(self):
        try:
            cur_long = self.cleaned_data['travel_from_longitude']
        except KeyError:
            raise ValidationError("please insert Address and Choice from list")
        return cur_long
    
    def clean_travel_to_longitude(self):
        try:
            cur_long = self.cleaned_data['travel_to_longitude']
        except KeyError:
            raise ValidationError("please insert Address and Choice from list")
        return cur_long