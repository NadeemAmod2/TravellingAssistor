from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from app_survey.models import mdl_travel, travel_types, mdl_report, mdl_report_activities, mdl_report_suggestions, TRAVEL_MODE_CHOICES, mdl_time_log
from app_survey.forms import frm_travel
from app_user.forms import PersonalInfoForm
from django.core.exceptions import ObjectDoesNotExist
from django.urls.base import reverse
from django.http.response import JsonResponse, HttpResponse
from datetime import datetime, date, timedelta
import time, googlemaps, json, random, requests, csv, copy

GOOGLE_API_KEY = "AIzaSyA3L3Q5rCMHsMgixN6s6x9Y7vaSOHLSoJ4"
gmaps = googlemaps.Client(GOOGLE_API_KEY)


def vw_move(request, dir, pos):
    try:
        cur_travel = mdl_travel.objects.get(position=pos, user=request.user)
    except ObjectDoesNotExist:
        pos -= 1
        cur_travel = mdl_travel.objects.get(position=pos, user=request.user)
    if dir == "left":
        prev_travel = mdl_travel.objects.get(position=pos - 1, user=request.user)
        cur_travel.position = prev_travel.position
        prev_travel.position += 1
        cur_travel.save()
        prev_travel.save()
        return JsonResponse({"status": "ok"})


def vw_intro(request):
    return render(request, "app_survey/intro.html", {})


class Suggestion:
    def __init__(self):
        self.suggestionFor = ""
        self.activities = []
        self.timeArrStartIndex = 0
        self.calculatedTimes = []
        self.duration = {}
        self.travelModes = []
        self.mode = "walking"
        self.calorieCost = 0.0
        self.gymCost = 0.0
        self.nearbyLocation = ""
        self.travelTime = 0

    def getOutputHTML(self):
        return ""


def getShortFormOfPurpose(purpose):
    if purpose == 'Go Home':
        purpose = 'Home'
    elif purpose == 'Work Related':
        purpose = 'Work'
    return purpose


def purposeStrList_LeftRight(travelActivities, indexFrom, indexTo):  # including 'indexFrom', not including 'indexTo'
    result = []
    for index in range(indexFrom, indexTo):
        if index == 0:
            purpose = "Home"
        else:
            purpose = getShortFormOfPurpose(travelActivities[index - 1].purpose.name)
        result.append(purpose)
    return result


def purposeStrList_Middle(listInitial, act1, act2, act3):
    result = listInitial
    acts = [act1, act2, act3]
    for act in acts:
        purpose = getShortFormOfPurpose(act)
        result.append("<font color='red'>" + purpose + "</font>")
    return result


def purposeStrList_Middle4(listInitial, act1, act2, act3, act4):
    result = listInitial
    acts = [act1, act2, act3, act4]
    for act in acts:
        purpose = getShortFormOfPurpose(act)
        result.append("<font color='red'>" + purpose + "</font>")
    return result


def purposeStrList_NonMand_Mand(listInitial, travelActivities, each_non_mand, each_mand):
    result = listInitial
    for index in range(each_non_mand + 1, each_mand + 1):
        purpose = getShortFormOfPurpose(travelActivities[index - 1].purpose.name)
        result.append(purpose)
    return result


def calcMinutes(calcTime):
    pos = str(calcTime).find('hour')
    if pos >= 0:
        hour = int(str(calcTime)[0:pos - 1])
    else:
        hour = 0
    pos2 = str(calcTime).find('mins')
    if pos2 >= 0:
        if pos == -1:
            min = int(str(calcTime)[0:pos2 - 1])
        else:
            min = int(str(calcTime)[(pos + 5):(pos2 - 1)])
    else:
        min = 0
    return hour * 60 + min


def calcCalorieCost(weight, calcTime, mode="walking"):
    if type(calcTime) == str:
        calcMinutesCalcTime = calcMinutes(calcTime)
    else:
        calcMinutesCalcTime = calcTime

    if mode == "walking":
        mul = 3.5
    else:
        mul = 6
    ret = round(7 * mul * weight / 200 * calcMinutesCalcTime, 2)   # ret = round(3.5 * mul * weight / 200 * calcMinutesCalcTime, 2)
    return str(ret)


def calcGymCost(cost_gym_perday, calorieCost):  # calorieCost : str
    return str(round(cost_gym_perday / 1000 * float(calorieCost), 2))


def getStringOfCalculationResult__Time_plus_Minute(strTime, intMinute):
    FMT = '%H:%M:%S'
    return (datetime.strptime(strTime, FMT) + timedelta(minutes=intMinute)).strftime(
        FMT)  # i.e.  print( (datetime.strptime("22:00:00", FMT) + timedelta(minutes=30)).strftime(FMT) )  ===> 22:30:00


def getTimeFromString(strTime):
    FMT = '%H:%M:%S'
    dateTime = datetime.strptime(strTime, FMT)
    return datetime.time(dateTime)
def getTimeFromStringWithZone(strTime):
    FMT = '%H:%M %p'
    dateTime = datetime.strptime(strTime, FMT)
    return datetime.time(dateTime)

def getArrDepTimeChoices(strTimeOrigin, strTimeChoices):
    #####   in case of letting users enter time
    # timeChoices = strTimeChoices.split(",")
    # ret = []
    # offset = ( datetime.combine(date.today(), getTimeFromStringWithZone(timeChoices[0])) - datetime.combine(date.today(), getTimeFromString(strTimeOrigin)) ).total_seconds() // 60
    # if offset > 30:
    #     offset = 30
    # ret.append(getStringOfCalculationResult__Time_plus_Minute(strTimeOrigin, offset / 2));
    # ret.append(getStringOfCalculationResult__Time_plus_Minute(strTimeOrigin, offset));
    # offset = (datetime.combine(date.today(), getTimeFromString(strTimeOrigin)) - datetime.combine(date.today(), getTimeFromStringWithZone(timeChoices[1]))).total_seconds() // 60
    # if offset > 30:
    #     offset = 30
    # ret.append(getStringOfCalculationResult__Time_plus_Minute(strTimeOrigin, -offset / 2));
    # ret.append(getStringOfCalculationResult__Time_plus_Minute(strTimeOrigin, -offset));
    # return ret

    #####   in case of letting users enter offsets
    timeOffsets = strTimeChoices.split(",")
    ret = []
    for i in range(0, 2):
        ret.append( getStringOfCalculationResult__Time_plus_Minute(strTimeOrigin, int(timeOffsets[i])) )
    return ret


dictCalculatedGMapTravelTimes = {}


def getDictKeyForGMapTravelTimeCalculation(srcLat, srcLong, dstLat, dstLong, mode):
    return f"{srcLat}_{srcLong}_{dstLat}_{dstLong}_{mode}"


def getGoogleMapTravelTimeInMinutes(srcLat, srcLong, dstLat, dstLong,
                                    mode="driving"):  # source-latitude, destination-Longitude,  mode is one of ["bicycling", "driving", "walking"]
    dictKeyForGMapTravelTimeCalculation = getDictKeyForGMapTravelTimeCalculation(srcLat, srcLong, dstLat, dstLong, mode)
    if dictKeyForGMapTravelTimeCalculation in dictCalculatedGMapTravelTimes:
        return dictCalculatedGMapTravelTimes[dictKeyForGMapTravelTimeCalculation]

    if mode == "driving":
        r = requests.get(
            f"https://maps.googleapis.com/maps/api/directions/json?origin={srcLat},{srcLong}&destination={dstLat},{dstLong}&mode=driving&key={GOOGLE_API_KEY}")
        data = r.json()
        if data['status'] == 'OK':
            ret = int(float(data['routes'][0]['legs'][0]['duration']['value']) / 60)
            dictCalculatedGMapTravelTimes[
                dictKeyForGMapTravelTimeCalculation] = ret  # save to dict to prevent repeated calculations
            return ret
        else:
            return 0

    dictKeyForGMapTravelTimeCalculation = getDictKeyForGMapTravelTimeCalculation(srcLat, srcLong, dstLat, dstLong,
                                                                                 "walking")
    if dictKeyForGMapTravelTimeCalculation in dictCalculatedGMapTravelTimes:
        ret = dictCalculatedGMapTravelTimes[dictKeyForGMapTravelTimeCalculation]
    else:
        r = requests.get(
            f"https://maps.googleapis.com/maps/api/directions/json?origin={srcLat},{srcLong}&destination={dstLat},{dstLong}&mode=walking&key={GOOGLE_API_KEY}")
        data = r.json()
        if data['status'] == 'OK':
            ret = int(float(data['routes'][0]['legs'][0]['duration']['value']) / 60)
            dictCalculatedGMapTravelTimes[dictKeyForGMapTravelTimeCalculation] = ret
        else:
            ret = 0

    if mode == "bicycling":
        dictKeyForGMapTravelTimeCalculation = getDictKeyForGMapTravelTimeCalculation(srcLat, srcLong, dstLat, dstLong, mode)
        mul2 = [0.3, 0.4, 0.5, 0.33, 0.35, 0.45, 0.58, 0.6, 0.54]
        ret = int(ret * random.choice(mul2))
        dictCalculatedGMapTravelTimes[dictKeyForGMapTravelTimeCalculation] = ret
    return ret

@login_required
def vw_step4(request):  # step4 ; showing suggestions
    if request.GET.get("calculated", "") == "":  # in case of loader-screen
        mdl_time_log.logTime(request.user.id, 3, datetime.now())
        return render(request, "app_survey/step4.html", {})

    travels = list(mdl_travel.objects.filter(user=request.user).order_by("position"))
    trvs = []
    for index, travel in enumerate(travels):
        if travel.purpose.name in ["Shopping", "Recreational", "Social", "Personal service"]:
            trvs.append({"position": travel.position, "travel": travel})
    results = []
    for travel in trvs:
        if travel["travel"].purpose_detail:
            params = {'location': (travel["travel"].travel_from_latitude, travel["travel"].travel_from_longitude),
                      'radius': 1000, 'type': travel["travel"].purpose_detail.name}
            result = gmaps.places_nearby(**params)
            results.append({"position": travel["position"], "result": json.dumps(result["results"]), "travel": travel})

    travelActivities = []
    nonMand = []
    mand = []
    for index, travel in enumerate(travels):
        if index != 1 or travel.travel_from != travel.travel_to:  # exception; this is because activity whose index is 1 (start from 0) is wrong ; it's previous developer's mistake
            travelActivities.append(travel)

    cntActivities = len(travelActivities)  # Remember that   cntPlaces == len(travelActivities) + 1
    arrHome = [0, cntActivities]
    locationFlex = [
        0]  # array to hold 0/1 which shows whether the activity (whose index is the index of this list) is location flexible or not.
    departureFlex = [0]  # 0/1 to show departure time is flexible or not
    arrivalFlex = [0]
    flexArr = []  # array to hold indexes of arrival-time flexibles
    flexDep = []  # array to hold indexes of departure-time flexibles
    for index, travel in enumerate(travelActivities):
        locationFlex.append(0)
        departureFlex.append(0)
        arrivalFlex.append(0)
        if index > 0:
            travel.travel_from_latitude = travelActivities[index - 1].travel_to_latitude  # also previous developer's mistake; travel_from_pos is not being saved correct, so I corrected it
            travel.travel_from_longitude = travelActivities[index - 1].travel_to_longitude
        if travel.purpose.name in ["Shopping", "Recreational", "Social", "Personal service"]:
            nonMand.append(index + 1)
        elif (not travel.last_activity) and (not travel.purpose.name == "Go Home"):
            mand.append(index + 1)
        for flex in mdl_travel.objects.get(id=travel.id).flexibles.all():
            if flex.name == "Location of destination":
                locationFlex[index + 1] = 1
            elif flex.name == "Departure time from source location":
                departureFlex[index] = 1
                flexDep.append(index)
            elif flex.name == "Arrival time at destination":
                arrivalFlex[index + 1] = 1
                flexArr.append(
                    index + 1)  # each activity has (departure-time, arrival-time);  i.e.  A -> B -> C -> D ====>  (depA, arrvB), (depB, arrvC), (depC, arrvD)
    nonFlexArr = []
    nonFlexDep = []
    for i in range(1, cntActivities + 1):
        if arrivalFlex[i] == 0:
            nonFlexArr.append(i)
    for i in range(0, cntActivities):
        if departureFlex[i] == 0:
            nonFlexDep.append(i)

    ########    Save activities to report_activities table   #########
    mdl_report_activities.objects.raw(f"DELETE FROM app_survey_mdl_report_activities WHERE person_id = {request.user.id}")

    dictTravelModes = dict(TRAVEL_MODE_CHOICES)
    i = 0
    for eachActivity in travelActivities:
        data = mdl_report_activities()
        data.person_id = request.user.id
        data.travel_from = eachActivity.travel_from
        data.travel_to = eachActivity.travel_to
        data.first_location = travelActivities[0].free_purpose
        data.departure_time = eachActivity.departure_time
        data.arrival_time = eachActivity.arrival_time
        data.travel_purpose = eachActivity.purpose.name
        data.travel_mode = dictTravelModes.get(eachActivity.travel_mode, "")
        data.flexible_departure = departureFlex[i]
        data.flexible_arrival = arrivalFlex[i + 1]
        data.flexible_location = locationFlex[i + 1]
        data.time_choices_arrival = eachActivity.time_choices_arrival
        data.time_choices_departure = eachActivity.time_choices_departure
        data.save()
        i += 1
    ############################          ############################

    RADIUS = 4000
    suggestions = []
    weight = travelActivities[0].user.weight
    cost_gym = travelActivities[0].user.cost_gym
    if cost_gym == 0:
        cost_gym = 15

    for each_non_mand in nonMand:
        if locationFlex[each_non_mand] == 1 and travelActivities[each_non_mand - 1].travel_mode in ["private_car", "motorcycle", "van", "opmv", "taxi", "droppted_car"]:
            for each_flex_arr in flexArr:
                if each_non_mand - each_flex_arr == -1:  # e.g.   home-shop-work-recreation-home ;   (1 - 2 == -1)
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_non_mand, each_flex_arr)
                    suggestionFor = f"Suggestion for flexible arrival to {getShortFormOfPurpose(travelActivities[each_flex_arr - 1].purpose.name)}"

                    # e.g.  home-shop-home-work-recreation-home
                    params = {'location': (travelActivities[each_non_mand - 1].travel_from_latitude,
                                           travelActivities[each_non_mand - 1].travel_from_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_1 = result["results"][:5]

                    arr_time_choice_1 = getArrDepTimeChoices(str(travelActivities[each_flex_arr - 1].arrival_time), str(travelActivities[each_flex_arr - 1].time_choices_arrival))
                    # each activity has (departure-time, arrival-time);  i.e.  A -> B -> C -> D ====>  (depA, arrvB), (depB, arrvC), (depC, arrvD)

                    for each_nearby in calc_non_mand_5_1:
                        for each_arr_time in arr_time_choice_1:
                            if departureFlex[each_non_mand - 1] == 1:
                                flag = True
                                for each_index in range(each_flex_arr + 1, cntActivities + 1):
                                    if arrivalFlex[each_index] == 0:
                                        flag = False
                                        break

                                calcTime2 = (datetime.combine(date.today(), travelActivities[
                                    each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                    each_non_mand - 1].arrival_time)).total_seconds() // 60
                                calcTime3 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_non_mand - 1].travel_from_latitude),
                                    str(travelActivities[each_non_mand - 1].travel_from_longitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_longitude))

                                activities = purposeStrList_LeftRight(travelActivities, 0, each_non_mand - 1)
                                purposeStrList_Middle(activities, travelActivities[each_non_mand - 1 - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1 - 1].purpose.name)
                                activities += purposeStrList_LeftRight(travelActivities,
                                                                       each_flex_arr if calcTime3 != 0 else each_flex_arr + 1,
                                                                       cntActivities + 1)

                                #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_non_mand - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_non_mand - 1].travel_from + "]</font>"        # exact locations

                                modes = ["walking", "bicycling"]
                                for mode in modes:
                                    suggestion = Suggestion()
                                    suggestion.nearbyLocation = each_nearby['name']
                                    suggestion.activities = activities
                                    suggestion.mode = mode
                                    suggestion.suggestionFor = suggestionFor
                                    suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}
                                    
                                    calcTime1 = getGoogleMapTravelTimeInMinutes(
                                        str(travelActivities[each_non_mand - 1].travel_from_latitude),
                                        str(travelActivities[each_non_mand - 1].travel_from_longitude),
                                        str(each_nearby['geometry']['location']['lat']),
                                        str(each_nearby['geometry']['location']['lng']), mode)
                                    calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                    suggestion.travelTime = calcTime1

                                    newDepartureTimeFromNonMand_1 = getStringOfCalculationResult__Time_plus_Minute(
                                        each_arr_time, -calcTime)
                                    suggestion.timeArrStartIndex = each_non_mand - 1
                                    suggestion.calculatedTimes += [("", newDepartureTimeFromNonMand_1), (
                                    getStringOfCalculationResult__Time_plus_Minute(newDepartureTimeFromNonMand_1,
                                                                                   calcTime1), ""), (
                                                                   getStringOfCalculationResult__Time_plus_Minute(
                                                                       newDepartureTimeFromNonMand_1,
                                                                       calcTime1 * 2 + calcTime2), "")]
                                    ## suggestions = suggestions + "<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;" + mode + " :&nbsp;&nbsp; [" + newDepartureTimeFromNonMand_1 + " --> " + getStringOfCalculationResult__Time_plus_Minute(newDepartureTimeFromNonMand_1, calcTime1) + " --> " + getStringOfCalculationResult__Time_plus_Minute(newDepartureTimeFromNonMand_1, calcTime1 * 2 + calcTime2)
                                    if calcTime3 != 0:
                                        suggestion.calculatedTimes.append((each_arr_time, ""))
                                    if departureFlex[each_flex_arr] == 1 and flag:
                                        offset = int((datetime.combine(date.today(), getTimeFromString(
                                            each_arr_time)) - datetime.combine(date.today(), travelActivities[
                                            each_flex_arr - 1].arrival_time)).total_seconds() / 60)
                                    else:
                                        offset = 0
                                    for i in range(each_flex_arr + 1, cntActivities + 1):
                                        suggestion.calculatedTimes.append((
                                                                          getStringOfCalculationResult__Time_plus_Minute(
                                                                              str(travelActivities[i - 1].arrival_time),
                                                                              offset), ""))

                                    calorieCost = calcCalorieCost(weight, calcTime1)
                                    gymCost = calcGymCost(cost_gym, calorieCost)
                                    suggestion.calorieCost = calorieCost
                                    suggestion.gymCost = gymCost
                                    ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                    suggestions.append(suggestion)

                            else:
                                flag = True
                                for each_index in range(each_flex_arr + 1, cntActivities + 1):
                                    if arrivalFlex[each_index] == 0:
                                        flag = False
                                        break

                                calcTime2 = (datetime.combine(date.today(), travelActivities[
                                    each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                    each_non_mand - 1].arrival_time)).total_seconds() // 60
                                calcTime3 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_non_mand - 1].travel_from_latitude),
                                    str(travelActivities[each_non_mand - 1].travel_from_longitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_longitude))

                                activities = purposeStrList_LeftRight(travelActivities, 0, each_non_mand - 1)
                                purposeStrList_Middle(activities, travelActivities[each_non_mand - 1 - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1 - 1].purpose.name)
                                activities += purposeStrList_LeftRight(travelActivities,
                                                                       each_flex_arr if calcTime3 != 0 else each_flex_arr + 1,
                                                                       cntActivities + 1)

                                #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_non_mand - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_non_mand - 1].travel_from + "]</font>"

                                modes = ["walking", "bicycling"]
                                for mode in modes:
                                    suggestion = Suggestion()
                                    suggestion.nearbyLocation = each_nearby['name']
                                    suggestion.activities = activities
                                    suggestion.mode = mode
                                    suggestion.suggestionFor = suggestionFor
                                    suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                    calcTime1 = getGoogleMapTravelTimeInMinutes(
                                        str(travelActivities[each_non_mand - 1].travel_from_latitude),
                                        str(travelActivities[each_non_mand - 1].travel_from_longitude),
                                        str(each_nearby['geometry']['location']['lat']),
                                        str(each_nearby['geometry']['location']['lng']), mode)
                                    calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                    suggestion.travelTime = calcTime1

                                    newDepartureTimeFromNonMand_1 = getStringOfCalculationResult__Time_plus_Minute(
                                        each_arr_time, -calcTime)
                                    if newDepartureTimeFromNonMand_1 >= str(
                                            travelActivities[each_non_mand - 1].departure_time):
                                        suggestion.timeArrStartIndex = each_non_mand - 1
                                        suggestion.calculatedTimes += [("", newDepartureTimeFromNonMand_1), (
                                        getStringOfCalculationResult__Time_plus_Minute(newDepartureTimeFromNonMand_1,
                                                                                       calcTime1), ""), (
                                                                       getStringOfCalculationResult__Time_plus_Minute(
                                                                           newDepartureTimeFromNonMand_1,
                                                                           calcTime1 * 2 + calcTime2), "")]
                                        if calcTime3 != 0:
                                            suggestion.calculatedTimes.append((each_arr_time, ""))

                                        if departureFlex[each_flex_arr] == 1 and flag:
                                            offset = int((datetime.combine(date.today(), getTimeFromString(
                                                each_arr_time)) - datetime.combine(date.today(), travelActivities[
                                                each_flex_arr - 1].arrival_time)).total_seconds() / 60)
                                        else:
                                            offset = 0
                                        for i in range(each_flex_arr + 1, cntActivities + 1):
                                            suggestion.calculatedTimes.append((
                                                                              getStringOfCalculationResult__Time_plus_Minute(
                                                                                  str(travelActivities[
                                                                                          i - 1].arrival_time), offset),
                                                                              ""))

                                        calorieCost = calcCalorieCost(weight, calcTime1)
                                        gymCost = calcGymCost(cost_gym, calorieCost)
                                        suggestion.calorieCost = calorieCost
                                        suggestion.gymCost = gymCost
                                        ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                        suggestions.append(suggestion)

                    # e.g.  home-work-shop-work-recreation-home
                    params = {'location': (travelActivities[each_flex_arr - 1].travel_to_latitude,
                                           travelActivities[each_flex_arr - 1].travel_to_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_2 = result["results"][:5]

                    for each_nearby in calc_non_mand_5_2:
                        for each_arr_time in arr_time_choice_1:
                            if departureFlex[each_non_mand - 1] == 1:
                                flag = True
                                for each_index in range(each_flex_arr + 1, cntActivities + 1):
                                    if arrivalFlex[each_index] == 0:
                                        flag = False
                                        break

                                calcTime2 = (datetime.combine(date.today(), travelActivities[
                                    each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                    each_non_mand - 1].arrival_time)).total_seconds() // 60
                                calcTime3 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_non_mand - 1].travel_from_latitude),
                                    str(travelActivities[each_non_mand - 1].travel_from_longitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_longitude))

                                activities = purposeStrList_LeftRight(travelActivities, 0,
                                                                      each_flex_arr - 1 if calcTime3 != 0 else each_flex_arr - 1 - 1)
                                purposeStrList_Middle(activities, travelActivities[each_flex_arr - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1].purpose.name,
                                                      travelActivities[each_flex_arr - 1].purpose.name)
                                activities += purposeStrList_LeftRight(travelActivities, each_flex_arr + 1,
                                                                       cntActivities + 1)

                                #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_flex_arr - 1].travel_to + " --> " + each_nearby["name"] + " --> " + travelActivities[each_flex_arr - 1].travel_to + "]</font>"

                                modes = ["walking", "bicycling"]
                                for mode in modes:
                                    suggestion = Suggestion()
                                    suggestion.nearbyLocation = each_nearby['name']
                                    suggestion.activities = activities
                                    suggestion.mode = mode
                                    suggestion.suggestionFor = suggestionFor
                                    suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                    calcTime1 = getGoogleMapTravelTimeInMinutes(
                                        str(travelActivities[each_flex_arr - 1].travel_to_latitude),
                                        str(travelActivities[each_flex_arr - 1].travel_to_longitude),
                                        str(each_nearby['geometry']['location']['lat']),
                                        str(each_nearby['geometry']['location']['lng']), mode)
                                    calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                    suggestion.travelTime = calcTime1

                                    newDepartureTimeFromNonMand_1 = getStringOfCalculationResult__Time_plus_Minute(
                                        each_arr_time, -calcTime)
                                    suggestion.timeArrStartIndex = each_non_mand - 1
                                    suggestion.calculatedTimes.append(("", newDepartureTimeFromNonMand_1))
                                    if calcTime3 != 0:
                                        suggestion.calculatedTimes.append((
                                                                          getStringOfCalculationResult__Time_plus_Minute(
                                                                              newDepartureTimeFromNonMand_1, calcTime3),
                                                                          ""))
                                    suggestion.calculatedTimes += [(getStringOfCalculationResult__Time_plus_Minute(
                                        newDepartureTimeFromNonMand_1, calcTime3 + calcTime1), ""), (each_arr_time, "")]

                                    if departureFlex[each_flex_arr] == 1 and flag:
                                        offset = (datetime.combine(date.today(),
                                                                   getTimeFromString(each_arr_time)) - datetime.combine(
                                            date.today(),
                                            travelActivities[each_flex_arr - 1].arrival_time)).total_seconds() // 60
                                    else:
                                        offset = 0
                                    for i in range(each_flex_arr + 1, cntActivities + 1):
                                        suggestion.calculatedTimes.append((
                                                                          getStringOfCalculationResult__Time_plus_Minute(
                                                                              str(travelActivities[i - 1].arrival_time),
                                                                              offset), ""))

                                    calorieCost = calcCalorieCost(weight, calcTime1)
                                    gymCost = calcGymCost(cost_gym, calorieCost)
                                    suggestion.calorieCost = calorieCost
                                    suggestion.gymCost = gymCost
                                    ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                    suggestions.append(suggestion)

                            else:
                                flag = True
                                for each_index in range(each_flex_arr + 1, cntActivities + 1):
                                    if arrivalFlex[each_index] == 0:
                                        flag = False
                                        break

                                calcTime2 = (datetime.combine(date.today(), travelActivities[
                                    each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                    each_non_mand - 1].arrival_time)).total_seconds() // 60
                                calcTime3 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_non_mand - 1].travel_from_latitude),
                                    str(travelActivities[each_non_mand - 1].travel_from_longitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_longitude))

                                activities = purposeStrList_LeftRight(travelActivities, 0,
                                                                      each_flex_arr - 1 if calcTime3 != 0 else each_flex_arr - 1 - 1)
                                purposeStrList_Middle(activities, travelActivities[each_flex_arr - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1].purpose.name,
                                                      travelActivities[each_flex_arr - 1].purpose.name)
                                activities += purposeStrList_LeftRight(travelActivities, each_flex_arr + 1,
                                                                       cntActivities + 1)
                                #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_flex_arr - 1].travel_to + " --> " + each_nearby["name"] + " --> " + travelActivities[each_flex_arr - 1].travel_to + "]</font>"

                                modes = ["walking", "bicycling"]
                                for mode in modes:
                                    suggestion = Suggestion()
                                    suggestion.nearbyLocation = each_nearby['name']
                                    suggestion.activities = activities
                                    suggestion.mode = mode
                                    suggestion.suggestionFor = suggestionFor
                                    suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                    calcTime1 = getGoogleMapTravelTimeInMinutes(
                                        str(travelActivities[each_flex_arr - 1].travel_to_latitude),
                                        str(travelActivities[each_flex_arr - 1].travel_to_longitude),
                                        str(each_nearby['geometry']['location']['lat']),
                                        str(each_nearby['geometry']['location']['lng']), mode)
                                    calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                    suggestion.travelTime = calcTime1

                                    newDepartureTimeFromNonMand_1 = getStringOfCalculationResult__Time_plus_Minute(
                                        each_arr_time, -calcTime)
                                    if newDepartureTimeFromNonMand_1 >= str(
                                            travelActivities[each_non_mand - 1].departure_time):
                                        suggestion.timeArrStartIndex = each_non_mand - 1
                                        suggestion.calculatedTimes.append(("", newDepartureTimeFromNonMand_1))
                                        if calcTime3 != 0:
                                            suggestion.calculatedTimes.append((
                                                                              getStringOfCalculationResult__Time_plus_Minute(
                                                                                  newDepartureTimeFromNonMand_1,
                                                                                  calcTime3), ""))
                                        suggestion.calculatedTimes += [(getStringOfCalculationResult__Time_plus_Minute(
                                            newDepartureTimeFromNonMand_1, calcTime3 + calcTime1), ""),
                                                                       (each_arr_time, "")]

                                        if departureFlex[each_flex_arr] == 1 and flag:
                                            offset = (datetime.combine(date.today(), getTimeFromString(
                                                each_arr_time)) - datetime.combine(date.today(), travelActivities[
                                                each_flex_arr - 1].arrival_time)).total_seconds() // 60
                                        else:
                                            offset = 0
                                        for i in range(each_flex_arr + 1, cntActivities + 1):
                                            suggestion.calculatedTimes.append((
                                                                              getStringOfCalculationResult__Time_plus_Minute(
                                                                                  str(travelActivities[
                                                                                          i - 1].arrival_time), offset),
                                                                              ""))

                                        calorieCost = calcCalorieCost(weight, calcTime1)
                                        gymCost = calcGymCost(cost_gym, calorieCost)
                                        suggestion.calorieCost = calorieCost
                                        suggestion.gymCost = gymCost
                                        ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                        suggestions.append(suggestion)

                elif each_non_mand - each_flex_arr == 1:  # e.g. home-work-shop-recreation-home   (2 - 1 == 1)
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_non_mand, each_flex_arr)
                    suggestionFor = f"Suggestion for flexible arrival to {getShortFormOfPurpose(travelActivities[each_flex_arr - 1].purpose.name)}"

                    # e.g.  home-shop-home-work-recreation-home
                    params = {'location': (travelActivities[each_flex_arr - 1].travel_from_latitude,
                                           travelActivities[each_flex_arr - 1].travel_from_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_1a = result["results"][:5]

                    arr_time_choice_1a = getArrDepTimeChoices(str(travelActivities[each_flex_arr - 1].arrival_time), str(travelActivities[each_flex_arr - 1].time_choices_arrival))
                    # each activity has (departure-time, arrival-time);  i.e.  A -> B -> C -> D ====>  (depA, arrvB), (depB, arrvC), (depC, arrvD)

                    for each_nearby in calc_non_mand_5_1a:
                        for each_arr_time in arr_time_choice_1a:
                            if departureFlex[each_flex_arr - 1] == 1:
                                flag = True
                                for each_index in range(each_non_mand + 1, cntActivities + 1):
                                    if arrivalFlex[each_index] == 0:
                                        flag = False
                                        break

                                calcTime2 = (datetime.combine(date.today(), travelActivities[
                                    each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                    each_non_mand - 1].arrival_time)).total_seconds() // 60
                                calcTime3 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_flex_arr - 1].travel_from_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_from_longitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_longitude))

                                activities = purposeStrList_LeftRight(travelActivities, 0, each_flex_arr - 1)
                                purposeStrList_Middle(activities, travelActivities[each_flex_arr - 1 - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1].purpose.name,
                                                      travelActivities[each_flex_arr - 1 - 1].purpose.name)
                                activities += purposeStrList_LeftRight(travelActivities, each_flex_arr,
                                                                       each_flex_arr + 1)
                                activities += purposeStrList_LeftRight(travelActivities, each_non_mand + 1,
                                                                       cntActivities + 1)
                                #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_flex_arr - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_flex_arr - 1].travel_from + "]</font>"

                                modes = ["walking", "bicycling"]
                                for mode in modes:
                                    suggestion = Suggestion()
                                    suggestion.nearbyLocation = each_nearby['name']
                                    suggestion.activities = activities
                                    suggestion.mode = mode
                                    suggestion.suggestionFor = suggestionFor
                                    suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                    calcTime1 = getGoogleMapTravelTimeInMinutes(
                                        str(travelActivities[each_flex_arr - 1].travel_from_latitude),
                                        str(travelActivities[each_flex_arr - 1].travel_from_longitude),
                                        str(each_nearby['geometry']['location']['lat']),
                                        str(each_nearby['geometry']['location']['lng']), mode)
                                    calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                    suggestion.travelTime = calcTime1

                                    newDepartureTimeFromFlexArr_1 = getStringOfCalculationResult__Time_plus_Minute(
                                        each_arr_time, -calcTime)
                                    suggestion.timeArrStartIndex = each_flex_arr - 1
                                    suggestion.calculatedTimes += [("", newDepartureTimeFromFlexArr_1), (
                                    getStringOfCalculationResult__Time_plus_Minute(newDepartureTimeFromFlexArr_1,
                                                                                   calcTime1), ""), (
                                                                   getStringOfCalculationResult__Time_plus_Minute(
                                                                       newDepartureTimeFromFlexArr_1,
                                                                       calcTime1 * 2 + calcTime2), ""),
                                                                   (each_arr_time, "")]

                                    if departureFlex[each_flex_arr] == 1 and flag:
                                        offset = int((datetime.combine(date.today(), getTimeFromString(
                                            each_arr_time)) - datetime.combine(date.today(), travelActivities[
                                            each_flex_arr - 1].arrival_time)).total_seconds() / 60)
                                    else:
                                        offset = 0
                                    for i in range(each_non_mand + 1, cntActivities + 1):
                                        suggestion.calculatedTimes.append((
                                                                          getStringOfCalculationResult__Time_plus_Minute(
                                                                              str(travelActivities[i - 1].arrival_time),
                                                                              offset), ""))

                                    calorieCost = calcCalorieCost(weight, calcTime1)
                                    gymCost = calcGymCost(cost_gym, calorieCost)
                                    suggestion.calorieCost = calorieCost
                                    suggestion.gymCost = gymCost
                                    ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                    suggestions.append(suggestion)

                            else:
                                flag = True
                                for each_index in range(each_non_mand + 1, cntActivities + 1):
                                    if arrivalFlex[each_index] == 0:
                                        flag = False
                                        break

                                calcTime2 = (datetime.combine(date.today(), travelActivities[
                                    each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                    each_non_mand - 1].arrival_time)).total_seconds() // 60
                                calcTime3 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_flex_arr - 1].travel_from_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_from_longitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_to_longitude))

                                activities = purposeStrList_LeftRight(travelActivities, 0, each_flex_arr - 1)
                                purposeStrList_Middle(activities, travelActivities[each_flex_arr - 1 - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1].purpose.name,
                                                      travelActivities[each_flex_arr - 1 - 1].purpose.name)
                                activities += purposeStrList_LeftRight(travelActivities, each_flex_arr,
                                                                       each_flex_arr + 1)
                                activities += purposeStrList_LeftRight(travelActivities, each_non_mand + 1,
                                                                       cntActivities + 1)

                                #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_flex_arr - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_flex_arr - 1].travel_from + "]</font>"

                                modes = ["walking", "bicycling"]
                                for mode in modes:
                                    suggestion = Suggestion()
                                    suggestion.nearbyLocation = each_nearby['name']
                                    suggestion.activities = activities
                                    suggestion.mode = mode
                                    suggestion.suggestionFor = suggestionFor
                                    suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                    calcTime1 = getGoogleMapTravelTimeInMinutes(
                                        str(travelActivities[each_flex_arr - 1].travel_from_latitude),
                                        str(travelActivities[each_flex_arr - 1].travel_from_longitude),
                                        str(each_nearby['geometry']['location']['lat']),
                                        str(each_nearby['geometry']['location']['lng']), mode)
                                    calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                    suggestion.travelTime = calcTime1

                                    newDepartureTimeFromFlexArr_1 = getStringOfCalculationResult__Time_plus_Minute(
                                        each_arr_time, -calcTime)
                                    if newDepartureTimeFromFlexArr_1 >= str(
                                            travelActivities[each_flex_arr - 1].departure_time):
                                        suggestion.timeArrStartIndex = each_flex_arr - 1
                                        suggestion.calculatedTimes += [("", newDepartureTimeFromFlexArr_1), (
                                        getStringOfCalculationResult__Time_plus_Minute(newDepartureTimeFromFlexArr_1,
                                                                                       calcTime1), ""), (
                                                                       getStringOfCalculationResult__Time_plus_Minute(
                                                                           newDepartureTimeFromFlexArr_1,
                                                                           calcTime1 * 2 + calcTime2), ""),
                                                                       (each_arr_time, "")]

                                        if departureFlex[each_flex_arr] == 1 and flag:
                                            offset = (datetime.combine(date.today(), getTimeFromString(
                                                each_arr_time)) - datetime.combine(date.today(), travelActivities[
                                                each_flex_arr - 1].arrival_time)).total_seconds() // 60
                                        else:
                                            offset = 0
                                        for i in range(each_non_mand + 1, cntActivities + 1):
                                            suggestion.calculatedTimes.append((
                                                                              getStringOfCalculationResult__Time_plus_Minute(
                                                                                  str(travelActivities[
                                                                                          i - 1].arrival_time), offset),
                                                                              ""))

                                        calorieCost = calcCalorieCost(weight, calcTime1)
                                        gymCost = calcGymCost(cost_gym, calorieCost)
                                        suggestion.calorieCost = calorieCost
                                        suggestion.gymCost = gymCost
                                        ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                        suggestions.append(suggestion)

                    # e.g.  home-work-shop-work-recreation-home
                    params = {'location': (travelActivities[each_flex_arr].travel_from_latitude,
                                           travelActivities[each_flex_arr].travel_from_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_2a = result["results"][:5]

                    for each_nearby in calc_non_mand_5_2a:
                        for each_arr_time in arr_time_choice_1a:
                            if departureFlex[each_flex_arr - 1] == 1:
                                flag = True
                                for each_index in range(each_non_mand + 1, cntActivities + 1):
                                    if arrivalFlex[each_index] == 0:
                                        flag = False
                                        break

                                calcTime2 = (datetime.combine(date.today(), travelActivities[
                                    each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                    each_non_mand - 1].arrival_time)).total_seconds() // 60
                                calcTime3 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_flex_arr - 1].travel_from_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_from_longitude),
                                    str(travelActivities[each_flex_arr].travel_from_latitude),
                                    str(travelActivities[each_flex_arr].travel_from_longitude))

                                activities = purposeStrList_LeftRight(travelActivities, 0, each_flex_arr)
                                purposeStrList_Middle(activities, travelActivities[each_flex_arr - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1].purpose.name,
                                                      travelActivities[each_flex_arr - 1].purpose.name)
                                activities += purposeStrList_LeftRight(travelActivities, each_non_mand + 1,
                                                                       cntActivities + 1)

                                #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_flex_arr].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_flex_arr].travel_from + "]</font>"

                                modes = ["walking", "bicycling"]
                                for mode in modes:
                                    suggestion = Suggestion()
                                    suggestion.nearbyLocation = each_nearby['name']
                                    suggestion.activities = activities
                                    suggestion.mode = mode
                                    suggestion.suggestionFor = suggestionFor
                                    suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                    calcTime1 = getGoogleMapTravelTimeInMinutes(
                                        str(travelActivities[each_flex_arr].travel_from_latitude),
                                        str(travelActivities[each_flex_arr].travel_from_longitude),
                                        str(each_nearby['geometry']['location']['lat']),
                                        str(each_nearby['geometry']['location']['lng']), mode)
                                    calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                    suggestion.travelTime = calcTime1

                                    newDepartureTimeFromFlexArr_1 = getStringOfCalculationResult__Time_plus_Minute(
                                        each_arr_time, -calcTime)
                                    suggestion.timeArrStartIndex = each_flex_arr - 1
                                    suggestion.calculatedTimes += [("", newDepartureTimeFromFlexArr_1), (
                                    getStringOfCalculationResult__Time_plus_Minute(newDepartureTimeFromFlexArr_1,
                                                                                   calcTime3), ""), (
                                                                   getStringOfCalculationResult__Time_plus_Minute(
                                                                       newDepartureTimeFromFlexArr_1,
                                                                       calcTime3 + calcTime1), ""), (each_arr_time, "")]

                                    if departureFlex[each_flex_arr] == 1 and flag:
                                        offset = (datetime.combine(date.today(),
                                                                   getTimeFromString(each_arr_time)) - datetime.combine(
                                            date.today(),
                                            travelActivities[each_flex_arr - 1].arrival_time)).total_seconds() // 60
                                    else:
                                        offset = 0
                                    for i in range(each_non_mand + 1, cntActivities + 1):
                                        suggestion.calculatedTimes.append((
                                                                          getStringOfCalculationResult__Time_plus_Minute(
                                                                              str(travelActivities[i - 1].arrival_time),
                                                                              offset), ""))

                                    calorieCost = calcCalorieCost(weight, calcTime1)
                                    gymCost = calcGymCost(cost_gym, calorieCost)
                                    suggestion.calorieCost = calorieCost
                                    suggestion.gymCost = gymCost
                                    ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                    suggestions.append(suggestion)

                            else:
                                flag = True
                                for each_index in range(each_non_mand + 1, cntActivities + 1):
                                    if arrivalFlex[each_index] == 0:
                                        flag = False
                                        break

                                calcTime2 = (datetime.combine(date.today(), travelActivities[
                                    each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                    each_non_mand - 1].arrival_time)).total_seconds() // 60
                                calcTime3 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_flex_arr - 1].travel_from_latitude),
                                    str(travelActivities[each_flex_arr - 1].travel_from_longitude),
                                    str(travelActivities[each_flex_arr].travel_from_latitude),
                                    str(travelActivities[each_flex_arr].travel_from_longitude))

                                activities = purposeStrList_LeftRight(travelActivities, 0, each_flex_arr)
                                purposeStrList_Middle(activities, travelActivities[each_flex_arr - 1].purpose.name,
                                                      travelActivities[each_non_mand - 1].purpose.name,
                                                      travelActivities[each_flex_arr - 1].purpose.name)
                                activities += purposeStrList_LeftRight(travelActivities, each_non_mand + 1,
                                                                       cntActivities + 1)
                                #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_flex_arr].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_flex_arr].travel_from + "]</font>"

                                modes = ["walking", "bicycling"]
                                for mode in modes:
                                    suggestion = Suggestion()
                                    suggestion.nearbyLocation = each_nearby['name']
                                    suggestion.activities = activities
                                    suggestion.mode = mode
                                    suggestion.suggestionFor = suggestionFor
                                    suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                    calcTime1 = getGoogleMapTravelTimeInMinutes(
                                        str(travelActivities[each_flex_arr].travel_from_latitude),
                                        str(travelActivities[each_flex_arr].travel_from_longitude),
                                        str(each_nearby['geometry']['location']['lat']),
                                        str(each_nearby['geometry']['location']['lng']), mode)
                                    calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                    suggestion.travelTime = calcTime1

                                    newDepartureTimeFromFlexArr_1 = getStringOfCalculationResult__Time_plus_Minute(
                                        each_arr_time, -calcTime)
                                    if newDepartureTimeFromFlexArr_1 >= str(
                                            travelActivities[each_flex_arr - 1].departure_time):
                                        suggestion.timeArrStartIndex = each_flex_arr - 1
                                        suggestion.calculatedTimes += [("", newDepartureTimeFromFlexArr_1), (
                                        getStringOfCalculationResult__Time_plus_Minute(newDepartureTimeFromFlexArr_1,
                                                                                       calcTime3), ""), (
                                                                       getStringOfCalculationResult__Time_plus_Minute(
                                                                           newDepartureTimeFromFlexArr_1,
                                                                           calcTime3 + calcTime1), ""),
                                                                       (each_arr_time, "")]
                                        if departureFlex[each_flex_arr] == 1 and flag:
                                            offset = (datetime.combine(date.today(), getTimeFromString(
                                                each_arr_time)) - datetime.combine(date.today(), travelActivities[
                                                each_flex_arr - 1].arrival_time)).total_seconds() // 60
                                        else:
                                            offset = 0
                                        for i in range(each_non_mand + 1, cntActivities + 1):
                                            suggestion.calculatedTimes.append((
                                                                              getStringOfCalculationResult__Time_plus_Minute(
                                                                                  str(travelActivities[
                                                                                          i - 1].arrival_time), offset),
                                                                              ""))

                                        calorieCost = calcCalorieCost(weight, calcTime1)
                                        gymCost = calcGymCost(cost_gym, calorieCost)
                                        suggestion.calorieCost = calorieCost
                                        suggestion.gymCost = gymCost
                                        ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                        suggestions.append(suggestion)

    # e.g.  home-work-shop-rec-home  ==> home-work-shop-work-rec-home ,  check for  2 - 1 == 1
    for each_non_mand in nonMand:
        if locationFlex[each_non_mand] == 1 and travelActivities[each_non_mand - 1].travel_mode in ["private_car", "motorcycle", "van", "opmv", "taxi", "droppted_car"]:
            for each_flex_dep in flexDep:
                if each_non_mand - each_flex_dep == 1:
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_non_mand, each_flex_dep)
                    suggestionFor = f"Suggestion for flexible departure from {getShortFormOfPurpose(travelActivities[each_flex_dep].purpose.name)}"

                    params = {'location': (travelActivities[each_flex_dep].travel_from_latitude,
                                           travelActivities[each_flex_dep].travel_from_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_3 = result["results"][:5]

                    dep_time_choice_1 = getArrDepTimeChoices(str(travelActivities[each_flex_dep].departure_time), str(travelActivities[each_flex_dep].time_choices_departure))
                    # each activity has (departure-time, arrival-time);  i.e.  A -> B -> C -> D ====>  (depA, arrvB), (depB, arrvC), (depC, arrvD)

                    for each_nearby in calc_non_mand_5_3:
                        for each_dep_time in dep_time_choice_1:
                            flag = True
                            for each_index in range(each_non_mand + 1, cntActivities + 1):
                                if arrivalFlex[each_index] == 0:
                                    flag = False
                                    break

                            calcTime2 = (datetime.combine(date.today(), travelActivities[
                                each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                                each_non_mand - 1].arrival_time)).total_seconds() // 60
                            calcTime3 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_flex_dep].travel_from_latitude),
                                str(travelActivities[each_flex_dep].travel_from_longitude),
                                str(travelActivities[each_non_mand + 1 - 1].travel_to_latitude),
                                str(travelActivities[each_non_mand + 1 - 1].travel_to_longitude))

                            activities = purposeStrList_LeftRight(travelActivities, 0, each_flex_dep)
                            purposeStrList_Middle(activities, travelActivities[each_flex_dep - 1].purpose.name,
                                                  travelActivities[each_non_mand - 1].purpose.name,
                                                  travelActivities[each_flex_dep - 1].purpose.name)
                            activities += purposeStrList_LeftRight(travelActivities,
                                                                   each_non_mand + 1 if calcTime3 != 0 else each_non_mand + 2,
                                                                   cntActivities + 1)

                            #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_flex_dep].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_flex_dep].travel_from + "]</font>"

                            modes = ["walking", "bicycling"]
                            for mode in modes:
                                suggestion = Suggestion()
                                suggestion.nearbyLocation = each_nearby['name']
                                suggestion.activities = activities
                                suggestion.mode = mode
                                suggestion.suggestionFor = suggestionFor
                                suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                calcTime1 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_flex_dep].travel_from_latitude),
                                    str(travelActivities[each_flex_dep].travel_from_longitude),
                                    str(each_nearby['geometry']['location']['lat']),
                                    str(each_nearby['geometry']['location']['lng']), mode)
                                calcTime = calcTime1 * 2 + calcTime2 + calcTime3
                                suggestion.travelTime = calcTime1

                                newArrivalTimeAtNonMandPlus1 = getStringOfCalculationResult__Time_plus_Minute(
                                    each_dep_time, calcTime)
                                suggestion.timeArrStartIndex = each_flex_dep
                                if flag:
                                    suggestion.calculatedTimes += [("", each_dep_time), (
                                    getStringOfCalculationResult__Time_plus_Minute(each_dep_time, calcTime1), ""), (
                                                                   getStringOfCalculationResult__Time_plus_Minute(
                                                                       each_dep_time, calcTime1 * 2 + calcTime2), "")]

                                    offset = (datetime.combine(date.today(), getTimeFromString(
                                        newArrivalTimeAtNonMandPlus1)) - datetime.combine(date.today(),
                                                                                          travelActivities[
                                                                                              each_non_mand + 1 - 1].arrival_time)).total_seconds() // 60
                                    for i in range(each_non_mand + 1 if calcTime3 != 0 else each_non_mand + 2,
                                                   cntActivities + 1):
                                        suggestion.calculatedTimes.append((
                                                                          getStringOfCalculationResult__Time_plus_Minute(
                                                                              str(travelActivities[i - 1].arrival_time),
                                                                              offset), ""))

                                    calorieCost = calcCalorieCost(weight, calcTime1)
                                    gymCost = calcGymCost(cost_gym, calorieCost)
                                    suggestion.calorieCost = calorieCost
                                    suggestion.gymCost = gymCost
                                    ## suggestions = suggestions + ",&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: ' + calcCalorieCost(weight, calcTime1)
                                    suggestions.append(suggestion)
                                else:
                                    if newArrivalTimeAtNonMandPlus1 <= str(
                                            travelActivities[each_non_mand + 1 - 1].arrival_time):
                                        suggestion.calculatedTimes += [("", each_dep_time), (getStringOfCalculationResult__Time_plus_Minute(each_dep_time, calcTime1), ""), (getStringOfCalculationResult__Time_plus_Minute(each_dep_time, calcTime1 * 2 + calcTime2), "")]
                                        if calcTime3 != 0:
                                            suggestion.calculatedTimes.append((newArrivalTimeAtNonMandPlus1, ""))

                                        for i in range(each_non_mand + 2, cntActivities + 1):
                                            suggestion.calculatedTimes.append((str(travelActivities[i - 1].arrival_time), ""))

                                        calorieCost = calcCalorieCost(weight, calcTime1)
                                        gymCost = calcGymCost(cost_gym, calorieCost)
                                        suggestion.calorieCost = calorieCost
                                        suggestion.gymCost = gymCost
                                        ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                        suggestions.append(suggestion)

    # e.g.  home-shop-recreation-work-home,   3 - 1 > 1
    for each_mand in mand:
        for each_non_mand in nonMand:
            if each_mand - each_non_mand >= 1:
                if arrivalFlex[each_mand + 1] == 1:  # suggestion will be home-recreation-work-home-shop-home
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_mand, each_non_mand)
                    suggestionFor = f"Suggestion for flexible arrival to {getShortFormOfPurpose(travelActivities[each_mand + 1 - 1].purpose.name)}"

                    params = {'location': (travelActivities[each_mand + 1 - 1].travel_to_latitude,
                                           travelActivities[each_mand + 1 - 1].travel_to_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_7 = result["results"][:5]
                    for each_nearby in calc_non_mand_5_7:
                        calcTime3 = getGoogleMapTravelTimeInMinutes(
                            str(travelActivities[each_non_mand - 1].travel_from_latitude),
                            str(travelActivities[each_non_mand - 1].travel_from_longitude),
                            str(travelActivities[each_non_mand + 1].travel_from_latitude),
                            str(travelActivities[each_non_mand + 1].travel_from_longitude))
                        calcTime2 = (datetime.combine(date.today(), travelActivities[each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[each_non_mand - 1].arrival_time)).total_seconds() // 60

                        activities = purposeStrList_LeftRight(travelActivities, 0, each_non_mand)
                        purposeStrList_NonMand_Mand(activities, travelActivities,
                                                    each_non_mand if calcTime3 != 0 else each_non_mand + 1, each_mand)
                        purposeStrList_Middle(activities, travelActivities[each_mand + 1 - 1].purpose.name,
                                              travelActivities[each_non_mand - 1].purpose.name,
                                              travelActivities[each_mand + 1 - 1].purpose.name)
                        if each_mand + 1 < cntActivities:
                            activities += purposeStrList_LeftRight(travelActivities, each_mand + 2, cntActivities + 1)

                        #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_mand + 1 - 1].travel_to + " --> " + each_nearby["name"] + " --> " + travelActivities[each_mand + 1 - 1].travel_to + "]</font>"

                        modes = ["walking", "bicycling"]
                        for mode in modes:
                            suggestion = Suggestion()
                            suggestion.nearbyLocation = each_nearby['name']
                            suggestion.activities = activities
                            suggestion.mode = mode
                            suggestion.suggestionFor = suggestionFor
                            suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                            calcTime1 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_mand + 1 - 1].travel_to_latitude),
                                str(travelActivities[each_mand + 1 - 1].travel_to_longitude),
                                str(each_nearby['geometry']['location']['lat']),
                                str(each_nearby['geometry']['location']['lng']), mode)
                            suggestion.travelTime = calcTime1                            

                            suggestion.timeArrStartIndex = each_non_mand - 1
                            suggestion.calculatedTimes.append(
                                ("", str(travelActivities[each_non_mand - 1].departure_time)))
                            if calcTime3 != 0:
                                suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                    str(travelActivities[each_non_mand - 1].departure_time), calcTime3), ""))
                            for i in range(each_non_mand + 2, each_mand + 1 + 1):
                                suggestion.calculatedTimes.append((str(travelActivities[i - 1].arrival_time), ""))
                            suggestion.calculatedTimes += [(getStringOfCalculationResult__Time_plus_Minute(
                                str(travelActivities[each_mand + 1 - 1].arrival_time), calcTime1), ""), (
                                                           getStringOfCalculationResult__Time_plus_Minute(
                                                               str(travelActivities[each_mand + 1 - 1].arrival_time),
                                                               calcTime1 * 2 + calcTime2), "")]

                            calorieCost = calcCalorieCost(weight, calcTime1)
                            gymCost = calcGymCost(cost_gym, calorieCost)
                            suggestion.calorieCost = calorieCost
                            suggestion.gymCost = gymCost
                            ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                            suggestions.append(suggestion)
                elif departureFlex[each_mand] == 1:  # suggestion will be home-recreation-work-shop-work-home
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_mand, each_non_mand)
                    suggestionFor = f"Suggestion for flexible departure from {getShortFormOfPurpose(travelActivities[each_mand].purpose.name)}"

                    params = {'location': (travelActivities[each_mand - 1].travel_to_latitude,
                                           travelActivities[each_mand - 1].travel_to_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_7b = result["results"][:5]
                    for each_nearby in calc_non_mand_5_7b:
                        calcTime3 = getGoogleMapTravelTimeInMinutes(
                            str(travelActivities[each_non_mand - 1].travel_from_latitude),
                            str(travelActivities[each_non_mand - 1].travel_from_longitude),
                            str(travelActivities[each_non_mand + 1].travel_from_latitude),
                            str(travelActivities[each_non_mand + 1].travel_from_longitude))
                        calcTime2 = (datetime.combine(date.today(), travelActivities[each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[each_non_mand - 1].arrival_time)).total_seconds() // 60

                        activities = purposeStrList_LeftRight(travelActivities, 0, each_non_mand)
                        purposeStrList_NonMand_Mand(activities, travelActivities, each_non_mand if calcTime3 != 0 else each_non_mand + 1, each_mand - 1)
                        purposeStrList_Middle(activities, travelActivities[each_mand - 1].purpose.name,
                                              travelActivities[each_non_mand - 1].purpose.name,
                                              travelActivities[each_mand - 1].purpose.name)
                        activities += purposeStrList_LeftRight(travelActivities, each_mand + 1, cntActivities + 1)

                        #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_mand - 1].travel_to + " --> " + each_nearby["name"] + " --> " + travelActivities[each_mand - 1].travel_to + "]</font>"

                        modes = ["walking", "bicycling"]
                        for mode in modes:
                            suggestion = Suggestion()
                            suggestion.nearbyLocation = each_nearby['name']
                            suggestion.activities = activities
                            suggestion.mode = mode
                            suggestion.suggestionFor = suggestionFor
                            suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                            calcTime1 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_mand - 1].travel_to_latitude),
                                str(travelActivities[each_mand - 1].travel_to_longitude),
                                str(each_nearby['geometry']['location']['lat']),
                                str(each_nearby['geometry']['location']['lng']), mode)
                            suggestion.travelTime = calcTime1

                            suggestion.timeArrStartIndex = each_non_mand - 1
                            suggestion.calculatedTimes.append(
                                ("", str(travelActivities[each_non_mand - 1].departure_time)))
                            if calcTime3 != 0:
                                suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                    str(travelActivities[each_non_mand - 1].departure_time), calcTime3), ""))
                            for i in range(each_non_mand + 2, each_mand + 1):
                                suggestion.calculatedTimes.append((str(travelActivities[i - 1].arrival_time), ""))
                            suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                str(travelActivities[each_mand - 1].arrival_time), calcTime1), ""))
                            suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                str(travelActivities[each_mand - 1].arrival_time), calcTime1 * 2 + calcTime2), ""))

                            calorieCost = calcCalorieCost(weight, calcTime1)
                            gymCost = calcGymCost(cost_gym, calorieCost)
                            suggestion.calorieCost = calorieCost
                            suggestion.gymCost = gymCost
                            ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                            suggestions.append(suggestion)
                elif departureFlex[each_mand] == 0 and arrivalFlex[
                    each_mand + 1] == 0:  # suggestion will be home-recreation-work-shop-work-home
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_mand, each_non_mand)
                    suggestionFor = f"Suggestion for flexible arrival to {getShortFormOfPurpose(travelActivities[each_mand + 1 - 1].purpose.name)}"

                    params = {'location': (travelActivities[each_mand - 1].travel_to_latitude,
                                           travelActivities[each_mand - 1].travel_to_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_7c = result["results"][:5]
                    for each_nearby in calc_non_mand_5_7c:
                        calcTime3 = getGoogleMapTravelTimeInMinutes(
                            str(travelActivities[each_non_mand - 1].travel_from_latitude),
                            str(travelActivities[each_non_mand - 1].travel_from_longitude),
                            str(travelActivities[each_non_mand + 1].travel_from_latitude),
                            str(travelActivities[each_non_mand + 1].travel_from_longitude))  # home - rec
                        calcTime2 = (datetime.combine(date.today(), travelActivities[
                            each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                            each_non_mand - 1].arrival_time)).total_seconds() // 60  # delay at shop
                        calcTime4 = (datetime.combine(date.today(),
                                                      travelActivities[each_mand].arrival_time) - datetime.combine(
                            date.today(), travelActivities[
                                each_mand].departure_time)).total_seconds() // 60  # original time taken for  work -> home

                        activities = purposeStrList_LeftRight(travelActivities, 0, each_non_mand)
                        purposeStrList_NonMand_Mand(activities, travelActivities,
                                                    each_non_mand if calcTime3 != 0 else each_non_mand + 1,
                                                    each_mand - 1)
                        purposeStrList_Middle(activities, travelActivities[each_mand - 1].purpose.name,
                                              travelActivities[each_non_mand - 1].purpose.name,
                                              travelActivities[each_mand - 1].purpose.name)
                        activities += purposeStrList_LeftRight(travelActivities, each_mand + 1, cntActivities + 1)

                        #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_mand - 1].travel_to + " --> " + each_nearby["name"] + " --> " + travelActivities[each_mand - 1].travel_to + "]</font>"

                        modes = ["walking", "bicycling"]
                        for mode in modes:
                            suggestion = Suggestion()
                            suggestion.nearbyLocation = each_nearby['name']
                            suggestion.activities = activities
                            suggestion.mode = mode
                            suggestion.suggestionFor = suggestionFor
                            suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                            calcTime1 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_mand - 1].travel_to_latitude),
                                str(travelActivities[each_mand - 1].travel_to_longitude),
                                str(each_nearby['geometry']['location']['lat']),
                                str(each_nearby['geometry']['location']['lng']), mode)  # work -> shop
                            suggestion.travelTime = calcTime1
                            calcTime5 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_mand].travel_from_latitude),
                                str(travelActivities[each_mand].travel_from_longitude),
                                str(travelActivities[each_mand].travel_to_latitude),
                                str(travelActivities[each_mand].travel_to_longitude), mode)  # carTT for  work -> home

                            if calcTime1 * 2 + calcTime2 + calcTime5 <= calcTime4:
                                suggestion.timeArrStartIndex = each_non_mand - 1
                                suggestion.calculatedTimes.append(("", str(travelActivities[each_non_mand - 1].departure_time)))
                                if calcTime3 != 0:
                                    suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                        str(travelActivities[each_non_mand - 1].departure_time), calcTime3), ""))
                                for i in range(each_non_mand + 2, each_mand + 1):
                                    suggestion.calculatedTimes.append((str(travelActivities[i - 1].arrival_time), ""))
                                suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                    str(travelActivities[each_mand - 1].arrival_time), calcTime1), ""))
                                suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                    str(travelActivities[each_mand - 1].arrival_time), calcTime1 * 2 + calcTime2), ""))

                                calorieCost = calcCalorieCost(weight, calcTime1)
                                gymCost = calcGymCost(cost_gym, calorieCost)
                                suggestion.calorieCost = calorieCost
                                suggestion.gymCost = gymCost
                                ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                suggestions.append(suggestion)

    # e.g.  home-work-rec-shop-home,   1 - 3 < -1, suggestion will be home-shop-home-work-rec-home
    for each_mand in mand:
        for each_non_mand in nonMand:
            if each_mand - each_non_mand < -1:
                if departureFlex[each_mand - 1] == 1:
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_mand, each_non_mand)
                    suggestionFor = f"Suggestion for flexible departure from {getShortFormOfPurpose(travelActivities[each_mand - 1].purpose.name)}"

                    params = {'location': (travelActivities[each_mand - 1].travel_from_latitude,
                                           travelActivities[each_mand - 1].travel_from_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_7a = result["results"][:5]
                    dep_time_choice_a = getArrDepTimeChoices(str(travelActivities[each_mand - 1].departure_time), str(travelActivities[each_mand - 1].time_choices_departure))
                    for each_nearby in calc_non_mand_5_7a:
                        for each_dep_time in dep_time_choice_a:
                            calcTime3 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_mand - 1].travel_from_latitude),
                                str(travelActivities[each_mand - 1].travel_from_longitude),
                                str(travelActivities[each_mand].travel_from_latitude),
                                str(travelActivities[each_mand].travel_from_longitude))  # home -> work  car-travel-time
                            calcTime4 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_non_mand - 1].travel_from_latitude),
                                str(travelActivities[each_non_mand - 1].travel_from_longitude),
                                str(travelActivities[each_non_mand + 1 - 1].travel_to_latitude),
                                str(travelActivities[each_non_mand + 1 - 1].travel_to_longitude))  # rec -> home  car-travel-time
                            calcTime2 = (datetime.combine(date.today(), travelActivities[each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[each_non_mand - 1].arrival_time)).total_seconds() // 60  # delayed time at shop

                            activities = purposeStrList_LeftRight(travelActivities, 0, each_mand - 1)
                            purposeStrList_Middle(activities, travelActivities[each_mand - 1 - 1].purpose.name,
                                                  travelActivities[each_non_mand - 1].purpose.name,
                                                  travelActivities[each_mand - 1 - 1].purpose.name)
                            activities += purposeStrList_LeftRight(travelActivities, each_mand, each_non_mand)
                            activities += purposeStrList_LeftRight(travelActivities, each_non_mand + 1, cntActivities + 1)

                            #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_mand - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_mand - 1].travel_from + "]</font>"

                            modes = ["walking", "bicycling"]
                            for mode in modes:
                                suggestion = Suggestion()
                                suggestion.nearbyLocation = each_nearby['name']
                                suggestion.activities = activities
                                suggestion.mode = mode
                                suggestion.suggestionFor = suggestionFor
                                suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                calcTime1 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_mand - 1].travel_from_latitude),
                                    str(travelActivities[each_mand - 1].travel_from_longitude),
                                    str(each_nearby['geometry']['location']['lat']),
                                    str(each_nearby['geometry']['location']['lng']),
                                    mode)  # home -> shop nearby place walk-travel-time
                                suggestion.travelTime = calcTime1

                                suggestion.timeArrStartIndex = each_mand - 1
                                suggestion.calculatedTimes += [("", each_dep_time), (
                                getStringOfCalculationResult__Time_plus_Minute(each_dep_time, calcTime1), ""), (
                                                               getStringOfCalculationResult__Time_plus_Minute(
                                                                   each_dep_time, calcTime1 + calcTime2 + calcTime1),
                                                               ""), (getStringOfCalculationResult__Time_plus_Minute(
                                    each_dep_time, calcTime1 + calcTime2 + calcTime1 + calcTime3),
                                                                     str(travelActivities[each_mand].departure_time))]
                                for i in range(each_mand + 1, each_non_mand):
                                    suggestion.calculatedTimes.append((str(travelActivities[i - 1].arrival_time), ""))
                                if each_non_mand < cntActivities:
                                    suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                        str(travelActivities[each_non_mand - 1].departure_time), calcTime4), ""))
                                    for i in range(each_non_mand + 2, cntActivities + 1):
                                        suggestion.calculatedTimes.append(
                                            (str(travelActivities[i - 1].arrival_time), ""))

                                calorieCost = calcCalorieCost(weight, calcTime1)
                                gymCost = calcGymCost(cost_gym, calorieCost)
                                suggestion.calorieCost = calorieCost
                                suggestion.gymCost = gymCost
                                ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                suggestions.append(suggestion)

                elif arrivalFlex[each_mand] == 1:
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_mand, each_non_mand)
                    suggestionFor = f"Suggestion for flexible arrival to {getShortFormOfPurpose(travelActivities[each_mand - 1].purpose.name)}"

                    params = {'location': (travelActivities[each_mand - 1].travel_from_latitude,
                                           travelActivities[each_mand - 1].travel_from_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_7b = result["results"][:5]
                    dep_time_choice_b = getArrDepTimeChoices(str(travelActivities[each_mand - 1].departure_time), str(travelActivities[each_mand - 1].time_choices_departure))
                    for each_nearby in calc_non_mand_5_7b:
                        for each_arr_time in dep_time_choice_b:
                            calcTime3 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_mand - 1].travel_from_latitude),
                                str(travelActivities[each_mand - 1].travel_from_longitude),
                                str(travelActivities[each_mand].travel_from_latitude),
                                str(travelActivities[each_mand].travel_from_longitude))  # home -> work  car-travel-time
                            calcTime4 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_non_mand - 1].travel_from_latitude),
                                str(travelActivities[each_non_mand - 1].travel_from_longitude),
                                str(travelActivities[each_non_mand + 1 - 1].travel_to_latitude), str(travelActivities[
                                                                                                         each_non_mand + 1 - 1].travel_to_longitude))  # rec -> home  car-travel-time
                            calcTime2 = (datetime.combine(date.today(), travelActivities[each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[each_non_mand - 1].arrival_time)).total_seconds() // 60  # delayed time at shop

                            activities = purposeStrList_LeftRight(travelActivities, 0, each_mand - 1)
                            purposeStrList_Middle(activities, travelActivities[each_mand - 1 - 1].purpose.name,
                                                  travelActivities[each_non_mand - 1].purpose.name,
                                                  travelActivities[each_mand - 1 - 1].purpose.name)
                            activities += purposeStrList_LeftRight(travelActivities, each_mand, each_non_mand)
                            activities += purposeStrList_LeftRight(travelActivities, each_non_mand + 1, cntActivities + 1)

                            #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_mand - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_mand - 1].travel_from + "]</font>"

                            modes = ["walking", "bicycling"]
                            for mode in modes:
                                suggestion = Suggestion()
                                suggestion.nearbyLocation = each_nearby['name']
                                suggestion.activities = activities
                                suggestion.mode = mode
                                suggestion.suggestionFor = suggestionFor
                                suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                                calcTime1 = getGoogleMapTravelTimeInMinutes(
                                    str(travelActivities[each_mand - 1].travel_from_latitude),
                                    str(travelActivities[each_mand - 1].travel_from_longitude),
                                    str(each_nearby['geometry']['location']['lat']),
                                    str(each_nearby['geometry']['location']['lng']),
                                    mode)  # home -> shop nearby place walk-travel-time
                                suggestion.travelTime = calcTime1

                                if getStringOfCalculationResult__Time_plus_Minute(
                                        str(travelActivities[each_mand - 1].departure_time),
                                        calcTime1 * 2 + calcTime2 + calcTime3) <= each_arr_time:
                                    suggestion.timeArrStartIndex = each_mand - 1
                                    suggestion.calculatedTimes += [
                                        ("", str(travelActivities[each_mand - 1].departure_time)), (
                                        getStringOfCalculationResult__Time_plus_Minute(
                                            str(travelActivities[each_mand - 1].departure_time), calcTime1), ""), (
                                        getStringOfCalculationResult__Time_plus_Minute(
                                            str(travelActivities[each_mand - 1].departure_time),
                                            calcTime1 + calcTime2 + calcTime1), ""), (each_arr_time, ""),
                                        ("", str(travelActivities[each_mand].departure_time))]
                                    for i in range(each_mand + 1, each_non_mand):
                                        suggestion.calculatedTimes.append(
                                            (str(travelActivities[i - 1].arrival_time), ""))
                                    if each_non_mand < cntActivities:
                                        suggestion.calculatedTimes.append((
                                                                          getStringOfCalculationResult__Time_plus_Minute(
                                                                              str(travelActivities[
                                                                                      each_non_mand - 1].departure_time),
                                                                              calcTime4), ""))
                                        for i in range(each_non_mand + 2, cntActivities + 1):
                                            suggestion.calculatedTimes.append(
                                                (str(travelActivities[i - 1].arrival_time), ""))
                                    calorieCost = calcCalorieCost(weight, calcTime1)
                                    gymCost = calcGymCost(cost_gym, calorieCost)
                                    suggestion.calorieCost = calorieCost
                                    suggestion.gymCost = gymCost
                                    ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                    suggestions.append(suggestion)

                elif arrivalFlex[each_mand] == 0 and departureFlex[each_mand - 1] == 0:
                    #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_mand, each_non_mand)
                    suggestionFor = ""

                    params = {'location': (travelActivities[each_mand - 1].travel_from_latitude,
                                           travelActivities[each_mand - 1].travel_from_longitude),
                              'radius': RADIUS,
                              'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                    result = gmaps.places_nearby(**params)
                    calc_non_mand_5_7c = result["results"][:5]
                    calcTimeOrigin = (datetime.combine(date.today(),
                                                       travelActivities[each_mand - 1].arrival_time) - datetime.combine(
                        date.today(), travelActivities[
                            each_mand - 1].departure_time)).total_seconds() // 60  # original time-taken of home ->work

                    for each_nearby in calc_non_mand_5_7c:
                        calcTime3 = getGoogleMapTravelTimeInMinutes(
                            str(travelActivities[each_mand - 1].travel_from_latitude),
                            str(travelActivities[each_mand - 1].travel_from_longitude),
                            str(travelActivities[each_mand].travel_from_latitude),
                            str(travelActivities[each_mand].travel_from_longitude))  # home -> work  car-travel-time
                        calcTime4 = getGoogleMapTravelTimeInMinutes(
                            str(travelActivities[each_non_mand - 1].travel_from_latitude),
                            str(travelActivities[each_non_mand - 1].travel_from_longitude),
                            str(travelActivities[each_non_mand + 1 - 1].travel_to_latitude), str(travelActivities[
                                                                                                     each_non_mand + 1 - 1].travel_to_longitude))  # rec -> home  car-travel-time
                        calcTime2 = int((datetime.combine(date.today(), travelActivities[
                            each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[
                            each_non_mand - 1].arrival_time)).total_seconds() / 60)  # delayed time at shop

                        activities = purposeStrList_LeftRight(travelActivities, 0, each_mand - 1)
                        purposeStrList_Middle(activities, travelActivities[each_mand - 1 - 1].purpose.name,
                                              travelActivities[each_non_mand - 1].purpose.name,
                                              travelActivities[each_mand - 1 - 1].purpose.name)
                        activities += purposeStrList_LeftRight(travelActivities, each_mand, each_non_mand)
                        activities += purposeStrList_LeftRight(travelActivities, each_non_mand + 1, cntActivities + 1)

                        #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_mand - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_mand - 1].travel_from + "]</font>"

                        modes = ["walking", "bicycling"]
                        for mode in modes:
                            suggestion = Suggestion()
                            suggestion.nearbyLocation = each_nearby['name']
                            suggestion.activities = activities
                            suggestion.mode = mode
                            suggestion.suggestionFor = suggestionFor
                            suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                            calcTime1 = getGoogleMapTravelTimeInMinutes(
                                str(travelActivities[each_mand - 1].travel_from_latitude),
                                str(travelActivities[each_mand - 1].travel_from_longitude),
                                str(each_nearby['geometry']['location']['lat']),
                                str(each_nearby['geometry']['location']['lng']),
                                mode)  # home -> shop nearby place walk-travel-time
                            suggestion.travelTime = calcTime1

                            if calcTime1 * 2 + calcTime2 + calcTime3 <= calcTimeOrigin:
                                suggestion.timeArrStartIndex = each_mand - 1
                                suggestion.calculatedTimes += [
                                    ("", str(travelActivities[each_mand - 1].departure_time)), (
                                    getStringOfCalculationResult__Time_plus_Minute(
                                        str(travelActivities[each_mand - 1].departure_time), calcTime1), ""), (
                                    getStringOfCalculationResult__Time_plus_Minute(
                                        str(travelActivities[each_mand - 1].departure_time),
                                        calcTime1 + calcTime2 + calcTime1), ""), (
                                    getStringOfCalculationResult__Time_plus_Minute(
                                        str(travelActivities[each_mand - 1].departure_time),
                                        calcTime1 + calcTime2 + calcTime1 + calcTime3),
                                    str(travelActivities[each_mand].departure_time))]
                                for i in range(each_mand + 1, each_non_mand):
                                    suggestion.calculatedTimes.append((str(travelActivities[i - 1].arrival_time), ""))
                                if each_non_mand < cntActivities:
                                    suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                        str(travelActivities[each_non_mand - 1].departure_time), calcTime4), ""))
                                    for i in range(each_non_mand + 2, cntActivities + 1):
                                        suggestion.calculatedTimes.append(
                                            (str(travelActivities[i - 1].arrival_time), ""))

                                calorieCost = calcCalorieCost(weight, calcTime1)
                                gymCost = calcGymCost(cost_gym, calorieCost)
                                suggestion.calorieCost = calorieCost
                                suggestion.gymCost = gymCost
                                ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                                suggestions.append(suggestion)

    # e.g.  home-shop2-work-recreation-shop1-home,   3 - 1 > 1,    4 - 1 > 1    ;   \
    #          3 - 1 ===> suggestion will be  home-work-recreation-shop1-shop2-shop1-home,     4 - 1 ===> home-work-recreation-shop1-home-shop2-home
    for each_non_mand1 in nonMand:
        for each_non_mand2 in nonMand:
            if each_non_mand1 - each_non_mand2 > 1 and arrivalFlex[each_non_mand1 + 1] == 1:
                #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_non_mand1, each_non_mand2)
                suggestionFor = f"Suggestion for flexible departure from {getShortFormOfPurpose(travelActivities[each_non_mand1 + 1 - 1].purpose.name)}"

                params = {'location': (travelActivities[each_non_mand1 + 1 - 1].travel_to_latitude,
                                       travelActivities[each_non_mand1 + 1 - 1].travel_to_longitude),
                          'radius': RADIUS,
                          'type': travelActivities[each_non_mand2 - 1].purpose_detail.name}
                result = gmaps.places_nearby(**params)
                calc_non_mand_5_8 = result["results"][:5]
                for each_nearby in calc_non_mand_5_8:
                    calcTime2 = (datetime.combine(date.today(), travelActivities[each_non_mand2].departure_time) - datetime.combine(date.today(), travelActivities[each_non_mand2 - 1].arrival_time)).total_seconds() // 60  # delayed-time at shop2
                    calcTime3 = getGoogleMapTravelTimeInMinutes(
                        str(travelActivities[each_non_mand2 - 1].travel_from_latitude),
                        str(travelActivities[each_non_mand2 - 1].travel_from_longitude),
                        str(travelActivities[each_non_mand2 + 1].travel_from_latitude), str(travelActivities[
                                                                                                each_non_mand2 + 1].travel_from_longitude))  # home -> work  car-travel-time

                    activities = purposeStrList_LeftRight(travelActivities, 0,
                                                          each_non_mand2 if calcTime3 != 0 else each_non_mand2 - 1)
                    purposeStrList_NonMand_Mand(activities, travelActivities, each_non_mand2, each_non_mand1)
                    purposeStrList_Middle(activities, travelActivities[each_non_mand1 + 1 - 1].purpose.name,
                                          travelActivities[each_non_mand2 - 1].purpose.name,
                                          travelActivities[each_non_mand1 + 1 - 1].purpose.name)
                    if each_non_mand1 + 1 < cntActivities:
                        activities += purposeStrList_LeftRight(travelActivities, each_non_mand1 + 2, cntActivities + 1)

                    #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_non_mand1 + 1 - 1].travel_to + " --> " + each_nearby["name"] + " --> " + travelActivities[each_non_mand1 + 1 - 1].travel_to + "]</font>"

                    modes = ["walking", "bicycling"]
                    for mode in modes:
                        suggestion = Suggestion()
                        suggestion.nearbyLocation = each_nearby['name']
                        suggestion.activities = activities
                        suggestion.mode = mode
                        suggestion.suggestionFor = suggestionFor
                        suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                        calcTime1 = getGoogleMapTravelTimeInMinutes(
                            str(travelActivities[each_non_mand1 + 1 - 1].travel_to_latitude),
                            str(travelActivities[each_non_mand1 + 1 - 1].travel_to_longitude),
                            str(each_nearby['geometry']['location']['lat']),
                            str(each_nearby['geometry']['location']['lng']),
                            mode)  # shop1 -> shop2 nearby place  walk-travel-time
                        suggestion.travelTime = calcTime1

                        suggestion.timeArrStartIndex = each_non_mand2 - 1
                        suggestion.calculatedTimes.append(
                            ("", str(travelActivities[each_non_mand2 - 1].departure_time)))
                        if calcTime3 != 0:
                            suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                                str(travelActivities[each_non_mand2 - 1].departure_time), calcTime3), ""))
                        for i in range(each_non_mand2 + 2, each_non_mand1 + 1 + 1):
                            suggestion.calculatedTimes.append((str(travelActivities[i - 1].arrival_time), ""))
                        suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                            str(travelActivities[each_non_mand1 + 1 - 1].arrival_time), calcTime1), ""))
                        suggestion.calculatedTimes.append((getStringOfCalculationResult__Time_plus_Minute(
                            str(travelActivities[each_non_mand1 + 1 - 1].arrival_time), calcTime1 * 2 + calcTime2), ""))

                        calorieCost = calcCalorieCost(weight, calcTime1)
                        gymCost = calcGymCost(cost_gym, calorieCost)
                        suggestion.calorieCost = calorieCost
                        suggestion.gymCost = gymCost
                        ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                        suggestions.append(suggestion)

    # e.g.  home-shop-work; if dep from home is unflexible and arrv at work is unflexible,  suggestion will be home-shopXX-home-work but only when walkTT[home -> shopXX] + walkTT[shopXX -> home] + carTT[home -> work] <= original_arrival_time_at_work  - original_departure_time_from_home
    for each_non_mand in nonMand:
        for each_non_flex_arr in nonFlexArr:
            if each_non_mand - each_non_flex_arr == -1 and departureFlex[
                each_non_mand - 1] == 0:  # e.g.   each_non_mand : 1,  each_non_flex_arr : 2
                #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_non_mand, each_non_flex_arr)
                suggestionFor = ""

                params = {'location': (travelActivities[each_non_mand - 1].travel_from_latitude,
                                       travelActivities[each_non_mand - 1].travel_from_longitude),
                          'radius': RADIUS,
                          'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                result = gmaps.places_nearby(**params)
                calc_non_mand_5_9 = result["results"][:5]
                for each_nearby in calc_non_mand_5_9:
                    calcTime2 = (datetime.combine(date.today(), travelActivities[each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[each_non_mand - 1].arrival_time)).total_seconds() // 60  # delayed-time at shop
                    calcTime3 = getGoogleMapTravelTimeInMinutes(
                        str(travelActivities[each_non_mand - 1].travel_from_latitude),
                        str(travelActivities[each_non_mand - 1].travel_from_longitude),
                        str(travelActivities[each_non_flex_arr - 1].travel_to_latitude), str(travelActivities[each_non_flex_arr - 1].travel_to_longitude))  # home -> work  car-travel-time

                    activities = purposeStrList_LeftRight(travelActivities, 0, each_non_mand - 1)
                    purposeStrList_Middle(activities, travelActivities[each_non_mand - 1 - 1].purpose.name,
                                          travelActivities[each_non_mand - 1].purpose.name, travelActivities[each_non_mand - 1 - 1].purpose.name)  # each_non_mand - 1 - 1 == -1 ;  list[-1] means the last item of list, so it means "home"
                    activities += purposeStrList_LeftRight(travelActivities,
                                                           each_non_mand + 1 if calcTime3 != 0 else each_non_mand + 2,
                                                           cntActivities + 1)

                    #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_non_mand - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_non_mand - 1].travel_from + "]</font>"

                    modes = ["walking", "bicycling"]
                    for mode in modes:
                        suggestion = Suggestion()
                        suggestion.nearbyLocation = each_nearby['name']
                        suggestion.activities = activities
                        suggestion.mode = mode
                        suggestion.suggestionFor = suggestionFor
                        suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                        calcTime1 = getGoogleMapTravelTimeInMinutes(
                            str(travelActivities[each_non_mand - 1].travel_from_latitude),
                            str(travelActivities[each_non_mand - 1].travel_from_longitude),
                            str(each_nearby['geometry']['location']['lat']),
                            str(each_nearby['geometry']['location']['lng']),
                            mode)  # home -> shop nearby place walk-travel-time
                        suggestion.travelTime = calcTime1

                        if calcTime1 + calcTime2 + calcTime1 + calcTime3 <= (datetime.combine(date.today(), travelActivities[each_non_mand + 1 - 1].arrival_time) - datetime.combine(date.today(), travelActivities[each_non_mand - 1].departure_time)).total_seconds() // 60:
                            suggestion.timeArrStartIndex = each_non_mand - 1
                            suggestion.calculatedTimes += [("",
                                                            str(travelActivities[each_non_mand - 1].departure_time)),
                                                           (getStringOfCalculationResult__Time_plus_Minute(str(travelActivities[each_non_mand - 1].departure_time), calcTime1), ""),
                                                           (getStringOfCalculationResult__Time_plus_Minute(str(travelActivities[each_non_mand - 1].departure_time), calcTime1 * 2 + calcTime2), ""),
                                                           (getStringOfCalculationResult__Time_plus_Minute(str(travelActivities[each_non_mand - 1].departure_time), calcTime1 * 2 + calcTime2 + calcTime3), "")]

                            calorieCost = calcCalorieCost(weight, calcTime1)
                            gymCost = calcGymCost(cost_gym, calorieCost)
                            suggestion.calorieCost = calorieCost
                            suggestion.gymCost = gymCost
                            ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                            suggestions.append(suggestion)

    # e.g.  home-work-shop; if dep from home is unflexible and arrv at work is unflexible,  suggestion will be home-shopXX-home-work but only when walkTT[home -> shopXX] + walkTT[shopXX -> home] + carTT[home -> work] <= original_arrival_time_at_work  - original_departure_time_from_home
    for each_non_mand in nonMand:
        for each_non_flex_arr in nonFlexArr:
            if each_non_mand - each_non_flex_arr == 1 and departureFlex[each_non_flex_arr - 1] == 0:  # e.g.   each_non_mand : 2,  each_non_flex_arr : 1
                #### suggestions = suggestions + " <br/><br/> check ({}, {}) ".format(each_non_mand, each_non_flex_arr)
                suggestionFor = ""

                params = {'location': (travelActivities[each_non_flex_arr - 1].travel_from_latitude,
                                       travelActivities[each_non_flex_arr - 1].travel_from_longitude),
                          'radius': RADIUS,
                          'type': travelActivities[each_non_mand - 1].purpose_detail.name}
                result = gmaps.places_nearby(**params)
                calc_non_mand_5_10 = result["results"][:5]
                for each_nearby in calc_non_mand_5_10:
                    calcTime2 = (datetime.combine(date.today(), travelActivities[each_non_mand].departure_time) - datetime.combine(date.today(), travelActivities[each_non_mand - 1].arrival_time)).total_seconds() // 60  # delayed-time at shop
                    calcTime3 = getGoogleMapTravelTimeInMinutes(
                        str(travelActivities[each_non_flex_arr - 1].travel_from_latitude),
                        str(travelActivities[each_non_flex_arr - 1].travel_from_longitude),
                        str(travelActivities[each_non_flex_arr - 1].travel_to_latitude), str(travelActivities[each_non_flex_arr - 1].travel_to_longitude))  # home -> work  car-travel-time

                    activities = purposeStrList_LeftRight(travelActivities, 0, each_non_flex_arr - 1)
                    purposeStrList_Middle4(activities, travelActivities[each_non_flex_arr - 1 - 1].purpose.name,
                                           travelActivities[each_non_mand - 1].purpose.name,
                                           travelActivities[each_non_flex_arr - 1 - 1].purpose.name, travelActivities[each_non_flex_arr - 1].purpose.name)  # each_non_flex_arr - 1 - 1 == -1 ;  list[-1] means the last item of list, so, in this example, it means "home"
                    activities += purposeStrList_LeftRight(travelActivities, each_non_mand + 1, cntActivities + 1)

                    #### suggestions = suggestions + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<font style='font-weight:bold'>[" + travelActivities[each_non_flex_arr - 1].travel_from + " --> " + each_nearby["name"] + " --> " + travelActivities[each_non_flex_arr - 1].travel_from + "]</font>"

                    modes = ["walking", "bicycling"]
                    for mode in modes:
                        suggestion = Suggestion()
                        suggestion.nearbyLocation = each_nearby['name']
                        suggestion.activities = activities
                        suggestion.mode = mode
                        suggestion.suggestionFor = suggestionFor
                        suggestion.duration = {'purpose': params['type'], 'duration': calcTime2}

                        calcTime1 = getGoogleMapTravelTimeInMinutes(
                            str(travelActivities[each_non_flex_arr - 1].travel_from_latitude),
                            str(travelActivities[each_non_flex_arr - 1].travel_from_longitude),
                            str(each_nearby['geometry']['location']['lat']),
                            str(each_nearby['geometry']['location']['lng']),
                            mode)  # home -> shop nearby place walk-travel-time
                        suggestion.travelTime = calcTime1

                        if calcTime1 + calcTime2 + calcTime1 + calcTime3 <= (datetime.combine(date.today(),
                                                                                              travelActivities[
                                                                                                  each_non_flex_arr - 1].arrival_time) - datetime.combine(
                                date.today(),
                                travelActivities[each_non_flex_arr - 1].departure_time)).total_seconds() // 60:
                            suggestion.timeArrStartIndex = each_non_flex_arr - 1
                            suggestion.calculatedTimes += [
                                ("", str(travelActivities[each_non_flex_arr - 1].departure_time)), (
                                getStringOfCalculationResult__Time_plus_Minute(
                                    str(travelActivities[each_non_flex_arr - 1].departure_time), calcTime1), ""), (
                                getStringOfCalculationResult__Time_plus_Minute(
                                    str(travelActivities[each_non_flex_arr - 1].departure_time),
                                    calcTime1 * 2 + calcTime2), ""), (getStringOfCalculationResult__Time_plus_Minute(
                                    str(travelActivities[each_non_flex_arr - 1].departure_time),
                                    calcTime1 * 2 + calcTime2 + calcTime3), "")]

                            calorieCost = calcCalorieCost(weight, calcTime1)
                            gymCost = calcGymCost(cost_gym, calorieCost)
                            suggestion.calorieCost = calorieCost
                            suggestion.gymCost = gymCost
                            ## suggestions = suggestions + "]&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  travel time: " + str(calcTime1) + " mins" + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; calorie cost: " + calorieCost + "&nbsp;&nbsp;, gym cost saved per week: " + gymCost
                            suggestions.append(suggestion)

    jsonSuggestions = json.dumps([suggestion.__dict__ for suggestion in suggestions])
    jsonTravelActivities = json.dumps([{'travelMode': ta.travel_mode, 'purpose': ta.purpose.name} for ta in travelActivities])
    return render(request, "app_survey/step4_calculated.html",
                  {"suggestions": jsonSuggestions, "travels": travels, "travelActivities": travelActivities,
                   "jsonTravelActivities": jsonTravelActivities})


@login_required
def vw_step5(request):  # step5 ; Sociodemographic questions
    return render(request, "app_survey/step5.html", {})


@login_required
def saveSuggestions(request):
    mdl_time_log.logTime(request.user.id, 4, datetime.now())

    suggestionsToSave = json.loads(request.POST.get("suggestions_to_save", []))

    ########    Save suggestions to report_suggestions table   #########
    i = 0
    for eachSuggestion in suggestionsToSave:
        data = mdl_report_suggestions()
        data.person_id = request.user.id
        data.suggestion_info = eachSuggestion["suggestionInfo"]
        data.suggestion_index = i + 1
        data.activity_purpose = eachSuggestion["duration"]["purpose"]
        data.location = eachSuggestion.get("nearbyLocation", "")
        data.travel_time = eachSuggestion["travelTime"]
        try:
            new_dep = []
            new_arr = []
            for ti in range(eachSuggestion["timeArrStartIndex"], len(eachSuggestion["calculatedTimes"])):
                new_dep.append( eachSuggestion["calculatedTimes"][ti][1] )
                new_arr.append( eachSuggestion["calculatedTimes"][ti][0] )

            if len(new_arr) > 0:
                data.calculated_time_arrival = ", ".join(new_arr)
            if len(new_dep) > 0:
                data.calculated_time_departure = ", ".join(new_dep)
        except:
            pass
        data.travel_mode = eachSuggestion.get("mode", "")
        data.calorie_cost = eachSuggestion.get("calorieCost", "")
        data.gymcost_saved = eachSuggestion.get("gymCost", "")
        data.accepted_by_user = eachSuggestion.get("accepted_by_user", "")
        data.save()
        i += 1
    ############################          ############################

    return JsonResponse({}, status=200)


@login_required
def saveDemographicInfos(request):
    mdl_time_log.logTime(request.user.id, 5, datetime.now())

    saveData = request.POST

    ########    Save to report table   #########
    data = mdl_report()
    data.person_id = request.user.id
    data.email = request.user.email
    data.weight = request.user.weight
    data.cost_gym = request.user.cost_gym
    data.gender = saveData.get("gender", "")
    data.marriage = saveData.get("marriage", "")
    data.age = saveData.get("age", "")
    data.employment_status = saveData.get("employment_status", "")
    data.student_category = saveData.get("student_category", "")
    data.study_level = saveData.get("study_level", "")
    data.ethnicity = saveData.get("ethnicity", "")
    data.cnt_household = saveData.get("cnt_household", "")
    data.cnt_children = saveData.get("cnt_children", "")
    data.cnt_cars = saveData.get("cnt_cars", "")
    data.cnt_bicycles = saveData.get("cnt_bicycles", "")
    data.cnt_motorbikes = saveData.get("cnt_motorbikes", "")
    data.driver_licence = saveData.get("driver_licence", "")
    data.annual_income = saveData.get("annual_income", "")
    data.internet_usage = saveData.get("internet_usage", "")
    data.internet_usage_entertain = saveData.get("internet_usage_entertain", "")
    data.internet_usage_shopping = saveData.get("internet_usage_shopping", "")
    data.cnt_days_per_week = saveData.get("cnt_days_per_week", "")
    data.save()
    ############################          ############################

    return redirect(vw_finish0)


@login_required
def exportCSV(request):
    response = HttpResponse(content_type='text/csv')
    dateToday = date.today()
    response[
        'Content-Disposition'] = f'attachment; filename="Report_{dateToday.year}-{dateToday.month}-{dateToday.day}.csv"'
    retCSVWriter = csv.writer(response)
    retCSVWriter.writerow(
        ['Person ID', 'Email ID', 'Travel from', 'Travel to', 'First location', 'Departure time for source', 'Arrival time for destination', 'Travel purpose', 'Travel mode', 'Flexible departure for source', 'Flexible arrival for destination', 'Flexible location', 'Arrival-time choice1', 'Arrival-time choice2', 'Departure-time choice1', 'Departure-time choice2', 'Weight', 'Gym cost per day',
         'Suggestion index', 'Suggestion info', 'Activity purpose', 'Location', 'Travel time', 'New/calculated arrival time', 'New/calculated departure time', 'Travel mode', 'Calorie cost', 'Gym cost saved', 'User accepted or not',
         'Gender', 'Marital status', 'Age range', 'Employment status', 'Student', 'Study level', 'Ethnicity', 'Number of people in', 'Number of children in', 'Number of cars in', 'Number of bicycles in', 'Number of motorbikes in', "Driver's Licence", 'Household income range', 'Usage of internet in a day', 'Usage of internet for shopping', 'Usage of internet for entertainment', 'Number of days per week', 'Time when clicked "Agree to participate"', 'Time when clicked the last "Next" button (activity)', 'Time when clicked "Show suggestions"', 'Time when clicked the last "Next" button (suggestions)', 'Time when clicked "Save & Finish"'])

    reportObjs = mdl_report.objects.raw("SELECT * FROM app_survey_mdl_report")
    for eachObj in reportObjs:
        reportActivityObjs = mdl_report.objects.raw(
            f"SELECT * FROM app_survey_mdl_report_activities ra WHERE ra.person_id = {eachObj.person_id}")
        reportSuggestionObjs = mdl_report.objects.raw(
            f"SELECT * FROM app_survey_mdl_report_suggestions rs WHERE rs.person_id = {eachObj.person_id}")
        reportTimeLogs = mdl_report.objects.raw(
            f"SELECT * FROM app_survey_mdl_time_log WHERE person_id = {eachObj.person_id}")
        nActivityObjs = len(reportActivityObjs)
        nSuggestionObjs = len(reportSuggestionObjs)
        nTimeLogs = len(reportTimeLogs)
        nMaxLen = max(nActivityObjs, nSuggestionObjs, nTimeLogs)
        nMinLen = min(nActivityObjs, nSuggestionObjs)

        for i in range(0, nMaxLen):
            try:
                timeChoiceArrival0 = reportActivityObjs[i].time_choices_arrival.split(",")[0]
                timeChoiceArrival1 = reportActivityObjs[i].time_choices_arrival.split(",")[1]
                timeChoiceDeparture0 = reportActivityObjs[i].time_choices_departure.split(",")[0]
                timeChoiceDeparture1 = reportActivityObjs[i].time_choices_departure.split(",")[1]
            except:
                timeChoiceArrival0 = ''
                timeChoiceArrival1 = ''
                timeChoiceDeparture0 = ''
                timeChoiceDeparture1 = ''
                pass

            rowToWrite = []
            if i < nMinLen:
                rowToWrite = [  eachObj.person_id, eachObj.email, reportActivityObjs[i].travel_from,
                                reportActivityObjs[i].travel_to, reportActivityObjs[i].first_location,
                                reportActivityObjs[i].departure_time, reportActivityObjs[i].arrival_time,
                                reportActivityObjs[i].travel_purpose, reportActivityObjs[i].travel_mode,
                                reportActivityObjs[i].flexible_departure, reportActivityObjs[i].flexible_arrival,
                                reportActivityObjs[i].flexible_location, timeChoiceArrival0, timeChoiceArrival1, timeChoiceDeparture0, timeChoiceDeparture1,
                                eachObj.weight, eachObj.cost_gym,
                                reportSuggestionObjs[i].suggestion_index, reportSuggestionObjs[i].suggestion_info, reportSuggestionObjs[i].activity_purpose, reportSuggestionObjs[i].location, reportSuggestionObjs[i].travel_time,
                                reportSuggestionObjs[i].calculated_time_arrival,
                                reportSuggestionObjs[i].calculated_time_departure,
                                reportSuggestionObjs[i].travel_mode, reportSuggestionObjs[i].calorie_cost,
                                reportSuggestionObjs[i].gymcost_saved, "Yes" if reportSuggestionObjs[i].accepted_by_user else "No", eachObj.gender, eachObj.marriage,
                                eachObj.age, eachObj.employment_status, eachObj.student_category,
                                eachObj.study_level, eachObj.ethnicity, eachObj.cnt_household,
                                eachObj.cnt_children, eachObj.cnt_cars, eachObj.cnt_bicycles,
                                eachObj.cnt_motorbikes, eachObj.driver_licence, eachObj.annual_income,
                                eachObj.internet_usage, eachObj.internet_usage_shopping,
                                eachObj.internet_usage_entertain, eachObj.cnt_days_per_week ]
            elif i >= nActivityObjs and i < nSuggestionObjs:
                rowToWrite = [  eachObj.person_id, eachObj.email, '', '', '', '', '', '', '', '', '', '', '', '', '', '', eachObj.weight,
                                eachObj.cost_gym, reportSuggestionObjs[i].suggestion_index, reportSuggestionObjs[i].suggestion_info, reportSuggestionObjs[i].activity_purpose, reportSuggestionObjs[i].location, reportSuggestionObjs[i].travel_time,
                                reportSuggestionObjs[i].calculated_time_arrival, reportSuggestionObjs[i].calculated_time_departure,
                                reportSuggestionObjs[i].travel_mode, reportSuggestionObjs[i].calorie_cost,
                                reportSuggestionObjs[i].gymcost_saved, "Yes" if reportSuggestionObjs[i].accepted_by_user else "No", eachObj.gender, eachObj.marriage, eachObj.age,
                                eachObj.employment_status, eachObj.student_category, eachObj.study_level, eachObj.ethnicity,
                                eachObj.cnt_household, eachObj.cnt_children, eachObj.cnt_cars, eachObj.cnt_bicycles,
                                eachObj.cnt_motorbikes, eachObj.driver_licence, eachObj.annual_income, eachObj.internet_usage,
                                eachObj.internet_usage_shopping, eachObj.internet_usage_entertain, eachObj.cnt_days_per_week ]
            elif i >= nSuggestionObjs and i < nActivityObjs:
                rowToWrite = [  eachObj.person_id, eachObj.email, reportActivityObjs[i].travel_from,
                                reportActivityObjs[i].travel_to, reportActivityObjs[i].first_location,
                                reportActivityObjs[i].departure_time, reportActivityObjs[i].arrival_time,
                                reportActivityObjs[i].travel_purpose, reportActivityObjs[i].travel_mode,
                                reportActivityObjs[i].flexible_departure, reportActivityObjs[i].flexible_arrival,
                                reportActivityObjs[i].flexible_location, timeChoiceArrival0, timeChoiceArrival1, timeChoiceDeparture0, timeChoiceDeparture1,
                                eachObj.weight, eachObj.cost_gym,
                                '', '', '', '', '', '', '', '', '', '', '',
                                eachObj.gender, eachObj.marriage, eachObj.age,
                                eachObj.employment_status, eachObj.student_category, eachObj.study_level,
                                eachObj.ethnicity, eachObj.cnt_household, eachObj.cnt_children, eachObj.cnt_cars,
                                eachObj.cnt_bicycles, eachObj.cnt_motorbikes, eachObj.driver_licence,
                                eachObj.annual_income, eachObj.internet_usage, eachObj.internet_usage_shopping,
                                eachObj.internet_usage_entertain, eachObj.cnt_days_per_week ]
            
            if i < nTimeLogs:
                rowToWrite += [reportTimeLogs[i].time1, reportTimeLogs[i].time2, reportTimeLogs[i].time3, reportTimeLogs[i].time4, reportTimeLogs[i].time5]
            else:
                rowToWrite += ['', '', '', '', '']
                
            retCSVWriter.writerow( rowToWrite )

    return response


@login_required
def vw_step3(request):
    travels = list(mdl_travel.objects.filter(user=request.user).order_by("position"))
    trvs = []

    for index, travel in enumerate(travels):
        if travel.purpose.name in ["Shopping", "Recreational", "Social", "Personal service"]:
            trvs.append({"position": travel.position, "travel": travel})

    results = []
    for travel in trvs:
        if travel["travel"].purpose_detail:
            params = {'location': (travel["travel"].travel_from_latitude, travel["travel"].travel_from_longitude),
                      'radius': 1000, 'type': travel["travel"].purpose_detail.name}
            result = gmaps.places_nearby(**params)
            results.append({"position": travel["position"], "result": json.dumps(result["results"]), "travel": travel})
    return render(request, "app_survey/step3.html",
                  {"results": results, "travels": travels})


@login_required
def vw_step2(request):
    mdl_time_log.logTime(request.user.id, 2, datetime.now())

    travels = list(mdl_travel.objects.filter(user=request.user).order_by("position"))
    trvs = []
    counter = 0
    for travel in travels:
        try:
            travel.flexible = list(travel.flexibles.all().values_list("name", flat=True))
            # travel.departure_time=travels[counter-1].departure_time
            travel.type = travel_types[travel.travel_mode]
            travel.travel_time = datetime.combine(date.today(), travel.arrival_time) - datetime.combine(date.today(),
                                                                                                        travel.departure_time)
            counter += 1
            trvs.append(travel)
        except IndexError:
            trvs.append(travel)
    data = copy.copy(request.POST)
    if data:
        if data['weight'] == '0':
            data['weight'] = '70'   # default weight as 70
    personalInfo = PersonalInfoForm(instance=request.user, data=data or None)
    if request.POST:
        if personalInfo.is_valid():
            personalInfo.save()
            return redirect(reverse("step3"))

    return render(request,
                  "app_survey/step2.html",
                  {"travels": travels, "personalInfo": personalInfo})


@login_required
def vw_step1(request):
    current_travel = request.GET.get("current_travel", "1")
    try:
        current_travel = int(current_travel)
    except ValueError:
        current_travel = 1

    if current_travel == 1 and not request.POST:
        mdl_time_log.logTime(request.user.id, 1, datetime.now())

    next_travel = current_travel
    exist_travel = None
    prev_travel = current_travel
    if prev_travel > 1:
        prev_travel -= 1
    prev_trav_object = None

    first_travel = None
    try:
        if current_travel == 1:
            exist_travel = mdl_travel.objects.get(position=0, user=request.user, session__isnull=True)
            first_travel = exist_travel
        else:
            exist_travel = mdl_travel.objects.get(position=current_travel, user=request.user, session__isnull=True)
    except ObjectDoesNotExist:
        pass

    initial = None
    if current_travel > 1:
        try:
            prev_trav_object = mdl_travel.objects.get(position=current_travel - 1, user=request.user,
                                                      session__isnull=True)
            initial = {
                'travel_from': prev_trav_object.travel_to,
                "travel_from_latitude": prev_trav_object.travel_from_latitude,
                "travel_from_longitude": prev_trav_object.travel_from_longitude,
            }
        except ObjectDoesNotExist:
            pass

    purpose_id = 0
    if request.POST:
        purpose_id = int(request.POST.get("purpose", "0")) if request.POST.get("purpose", "0") else 0
    if not purpose_id:
        if exist_travel:
            purpose_id = exist_travel.purpose.id
    cur_travel_form = frm_travel(instance=exist_travel, data=request.POST or None, initial=initial, purpose=purpose_id)
    if request.POST:
        if cur_travel_form.is_valid():
            cur_travel = cur_travel_form.save(commit=False)
            
            if current_travel == 1:
                cur_travel.position = 0
            else:
                cur_travel.position = current_travel
            cur_travel.user = request.user
            cur_travel.save()
            cur_travel_form.save_m2m()
            next_travel = current_travel + 1
            cur_travel_form = frm_travel()
            if current_travel == 1:
                travel1 = None
                try:
                    travel1 = mdl_travel.objects.get(position=1, user=request.user)
                except ObjectDoesNotExist:
                    pass
                travel = mdl_travel.objects.get(id=cur_travel.id)
                travel.travel_from = cur_travel.travel_to
                travel.position = 1
                travel.pk = travel1.id if travel1 else None
                travel.save()
                for flex in mdl_travel.objects.get(id=cur_travel.id).flexibles.all():
                    travel.flexibles.add(flex)

            if cur_travel.last_activity:
                return redirect(reverse("step2"))
            else:
                return redirect("/survey/step1/?current_travel=" + str(next_travel))

    return render(request, "app_survey/step1.html",
                  {
                      "next_travel": next_travel,
                      "prev_travel": prev_travel,
                      "current_travel": current_travel,
                      "frm_travel": cur_travel_form,
                      "prev_trav_object": prev_trav_object,
                      "exist_travel": exist_travel
                  })


@login_required
def get_purpose_detail(request, purpose_id):
    cur_frm_travel = frm_travel(purpose=purpose_id)
    return render(request, "app_survey/tpl_frm_pupose_detail.html",
                  {"frm_travel": cur_frm_travel})


def vw_finish0(request):
    return render(request, "app_survey/finish0.html", {})
