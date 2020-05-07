from django.db import models, connection
from django.contrib.auth import get_user_model
import datetime
from django.utils.timesince import timesince
# Create your models here.

PURPOSE_CHOICES=(
    ("accompany_someone","Accompany Someone"),
    ("shopping","Shopping"),
    ("change_mode","Change Mode"),
    ("education","Education"),
    ("go_home","Go Home"),
    ("other_purpose","Other Purpose"),
    ("personal_business","Personal Business"),
    ("pickup_deliver_something","Pickup/Deliver Something"),
    ("pickup_drop_off_someone","Pickup/Drop-off Someone"),
    ("recreational","Recreational"),
    ("social","Social"),
    ("personal_service","Personal service"),
    ("unknown_purpose","Unknown Purpose (at start of day)"),
    ("work_related","Work Related"),
    )

TRAVEL_MODE_CHOICES=(
    ("private_car","Private Car"),
    ("motorcycle","Motorcycle"),
    ("van","Van"),
    ("opmv","Other private motorized vehicle"),
    ("taxi","Taxi"),
    ("droppted_car","Dropped by someone on car"),
    ("shared_ride","Shared ride service"),
    ("pub_trans_train","Public transport(Train/Tram/Light rail service only)"),
    ("pub_trans_bus","Public Transport(Bus only)"),
    ("pub_trans_bus_train","Public transport(both train/tram/light rail service and bus)"),
    ("walking","Walking"),
    ("private_bicycle","Private Bicycle"),
    ("shared_bike","Shared bike service"),
    ("other","Other"),
    )

travel_types={
    "private_car":"car",
    "motorcycle":"car",
    "van":"car",
    "opmv":"car",
    "taxi":"car",
    "droppted_car":"car",
    "shared_ride":"car",
    "pub_trans_train":"public",
    "pub_trans_bus":"public",
    "pub_trans_bus_train":"public",
    "walking":"walking",
    "private_bicycle":"walking",
    "shared_bike":"walking",
    "other":"car",    
    }
    
class travel_mode_choices:
    private_car="private_car"
    motorcycle="motorcycle"
    van="van"
    opmv="opmv"
    taxi="taxi"
    droppted_car="droppted_car"
    shared_ride="shared_ride"
    pub_trans_train="pub_trans_train"
    pub_trans_bus="pub_trans_bus"
    pub_trans_bus_train="pub_trans_bus_train"
    walking="walking"
    private_bicycle="private_bicycle"
    shared_bike="shared_bike"
    other="other"
    
class purpose_choices_dict:
    accompany_someone="accompany_someone"
    shopping="shopping"
    change_mode="change_mode"
    education="education"
    go_home="go_home"
    other_purpose="other_purpose"
    personal_business="personal_business"
    pickup_deliver_something="pickup_deliver_something"
    pickup_drop_off_someone="pickup_drop_off_someone"
    recreational="recreational"
    social="social"
    personal_service="personal_service"
    unknown_purpose="unknown_purpose"
    work_related="work_related"
    

mdl_user=get_user_model()

class mdl_purpose(models.Model):
    name=models.CharField(max_length=200)
    class Meta:
        verbose_name = 'Purpose'
    def __str__(self):
        return "%s" % (self.name)
    
class mdl_purpose_detail(models.Model):
    name=models.CharField(max_length=200)
    purpose=models.ForeignKey(mdl_purpose,on_delete=models.DO_NOTHING)
    class Meta:
        verbose_name = 'Purpose Detail'
        unique_together=(
                        ("name","purpose"),
                        )
    def __str__(self):
        return "%s > %s " % (self.purpose,self.name)
    
    
    
    
class mdl_flexibility(models.Model):
    name= models.CharField(max_length=30)
    class Meta:
        verbose_name = 'Flexibility'
    def __str__(self):
        return "%s" % (self.name)

    
class mdl_travel(models.Model):
    session=models.IntegerField(blank=True,null=True)
    user=models.ForeignKey(mdl_user,on_delete=models.CASCADE)
    travel_from=models.CharField(max_length=254)
    travel_from_latitude = models.DecimalField(
                max_digits=23, decimal_places=15, null=True, blank=True)

    travel_from_longitude = models.DecimalField(
                max_digits=23, decimal_places=15, null=True, blank=True)
    departure_time=models.TimeField()
    travel_to=models.CharField(max_length=254)
    travel_to_latitude = models.DecimalField(
                max_digits=23, decimal_places=15, null=True, blank=True)

    travel_to_longitude = models.DecimalField(
                max_digits=23, decimal_places=15, null=True, blank=True)
    arrival_time=models.TimeField( null=True, blank=True)
    position=models.IntegerField()
    travel_mode=models.CharField(max_length=128,choices=TRAVEL_MODE_CHOICES)
    flexibles=models.ManyToManyField(mdl_flexibility,blank=True)
    purpose=models.ForeignKey(mdl_purpose,on_delete=models.DO_NOTHING)
    purpose_detail=models.ForeignKey(mdl_purpose_detail,
                                     on_delete=models.DO_NOTHING,blank=True,null=True)
    free_purpose=models.CharField(max_length=128, null=True, blank=True)
    last_activity=models.BooleanField(choices=((True,"Yes"), (False,"No")) ,default=False)
    type=models.CharField(max_length=30,choices=(("primary","Primary"),("suggestion","Suggestion")),default="primary")
    time_choices_arrival = models.CharField(max_length=50, null=True, blank=True)
    time_choices_departure = models.CharField(max_length=50, null=True, blank=True)

    """def get_max_reach(self):
        if self.max_reach:
            dummydate = datetime.date(2000,1,1)  # Needed to convert time to a datetime object
            dt1 = datetime.datetime.combine(dummydate,self.arrival_time)
            dt2 = datetime.datetime.combine(dummydate,self.max_reach)
            #print(dt1)
            #print(dt2)
            return timesince(dt1, dt2)
        else:
            return 0 
    """
    class Meta:
        verbose_name = 'Travel'
    
    def __str__(self):
        return "%s -- %s > %s by %s" % (self.user,
                                       self.travel_from,
                                       self.travel_to,
                                       self.travel_mode)

class mdl_report(models.Model):
    person_id = models.IntegerField()
    email = models.EmailField(verbose_name='email address', default="")
    weight = models.IntegerField(blank=True, default=0)
    cost_gym = models.FloatField(blank=True, default=0)
    gender = models.CharField(max_length=10, default="")
    marriage = models.CharField(max_length=10, default="")
    age = models.CharField(max_length=50, default="")
    employment_status = models.CharField(max_length=50, default="")
    student_category = models.CharField(max_length=50, default="")
    study_level = models.CharField(max_length=50, default="")
    ethnicity = models.CharField(max_length=50, default="")
    cnt_household = models.CharField(max_length=50, default="")
    cnt_children = models.CharField(max_length=50, default="")
    cnt_cars = models.CharField(max_length=50, default="")
    cnt_bicycles = models.CharField(max_length=50, default="")
    cnt_motorbikes = models.CharField(max_length=50, default="")
    driver_licence = models.CharField(max_length=50, default="")
    annual_income = models.CharField(max_length=50, default="")
    internet_usage = models.CharField(max_length=50, default="")
    internet_usage_entertain = models.CharField(max_length=50, default="")
    internet_usage_shopping = models.CharField(max_length=50, default="")
    cnt_days_per_week = models.CharField(max_length=50, default="")

    def __str__(self):
        return self.email

class mdl_report_activities(models.Model):
    person_id = models.IntegerField()
    travel_from = models.CharField(max_length=254)
    travel_to = models.CharField(max_length=254)
    first_location = models.CharField(max_length=254, null=True)
    departure_time = models.TimeField(blank=True, null=True)
    arrival_time = models.TimeField(blank=True, null=True)
    travel_purpose = models.CharField(max_length=50)
    travel_mode = models.CharField(max_length=50)
    flexible_departure = models.CharField(max_length=50)
    flexible_arrival = models.CharField(max_length=50)
    flexible_location = models.CharField(max_length=50)
    time_choices_arrival = models.CharField(max_length=10, null=True)
    time_choices_departure = models.CharField(max_length=10, null=True)

    def __str__(self):
        return f"{self.person_id}"

class mdl_report_suggestions(models.Model):
    person_id = models.IntegerField()
    suggestion_info = models.CharField(max_length= 254, null=True)
    suggestion_index = models.IntegerField(null=True)
    activity_purpose = models.CharField(max_length=50)
    location = models.CharField(max_length=254)
    travel_time = models.IntegerField(blank=True, default=0)
    calculated_time_arrival = models.CharField(max_length=254)
    calculated_time_departure = models.CharField(max_length=254)
    travel_mode = models.CharField(max_length=50)
    calorie_cost = models.FloatField(blank=True, default=0)
    gymcost_saved = models.FloatField(blank=True, default=0)
    accepted_by_user = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.person_id}"

class mdl_time_log(models.Model):
    person_id = models.IntegerField()
    time1 = models.DateTimeField()
    time2 = models.DateTimeField()
    time3 = models.DateTimeField()
    time4 = models.DateTimeField()
    time5 = models.DateTimeField()

    def __str__(self):
        return  f"""Time when user clicks 'Agree to participate' : {self.time1} \n
                    Time when user clicks the last 'next' button (activities) : {self.time2} \n 
                    Time when user clicks 'Show suggestions' : {self.time3} \n
                    Time when user clicks the last 'next' button (suggestions) : {self.time4} \n
                    Time when user clicks 'Save & Finish' (sociodemographic questions) : {self.time5} \n"""
    @staticmethod
    def logTime(userid, index, time):
        with connection.cursor() as cursor:
            if index == 1:
                cursor.execute(f"INSERT INTO app_survey_mdl_time_log (person_id, time1, time2, time3, time4, time5) VALUES({userid}, '{time}', '{time}', '{time}', '{time}', '{time}')")
            else:
                cursor.execute(f"UPDATE app_survey_mdl_time_log SET time{index} = '{time}' WHERE id = (SELECT MAX(id) FROM app_survey_mdl_time_log WHERE person_id = {userid})")
        