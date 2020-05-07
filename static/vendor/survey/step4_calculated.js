var suggestions = []
var travelActivities = []
var selectedSuggestions = []
var index = 0
var urlForStep5 = ""

function updateView() {
    if (suggestions.length == 0) {
        $('table.suggestions').hide()
        alert("No suggestion was calculated for you by our algorithm !")
        location.href = urlForStep5
        return
    }
    $("#suggestionNo").html(index + 1)
    $("#calorieCost").html(suggestions[index].calorieCost)
    $("#gymCost").html(suggestions[index].gymCost)
    $("#suggestion-for").html(suggestions[index].suggestionFor)
    $("#purpose").html(suggestions[index].duration['purpose'])
    $("#duration").html(suggestions[index].duration['duration'])

    var tr = $(".activity-row").first()
    var trHTML = "<td class='suggestion'></td>"
    for (var i = 0; i < suggestions[index].activities.length; i++) {
        if (i == 0) suggestions[index].suggestionInfo = ""
        var activity = suggestions[index].activities[i]
        var activityReal = activity.replace("<font color='red'>", "").replace("</font>", "")

        trHTML += `<td class='suggestion'>${activity}`
        suggestions[index].suggestionInfo += `${activityReal}`
        if (i < suggestions[index].activities.length - 1) {
            trHTML += `<i class="arrow_right fa fa-arrow-right ml-2 fa-2x"></i>`
            suggestions[index].suggestionInfo += " -> "
        }
        trHTML += `</td>`
    }
    tr.html(trHTML)

    tr = $(".calculated-time-row").first()
    trHTML = `<td class='suggestion strong'>Newly-calculated time <font class='time-arrival'>Arrival</font> | <font class='time-departure'>Departure</font></td>`
    for (i = 0; i < suggestions[index].timeArrStartIndex; i++)
        trHTML += `<td class='suggestion'></td>`
    for (i = suggestions[index].timeArrStartIndex; i < suggestions[index].activities.length; i++) {
        trHTML += `<td class='suggestion'>`
        j = i - suggestions[index].timeArrStartIndex
        time_Arr_Dep = suggestions[index].calculatedTimes[j]
        if (time_Arr_Dep == null || time_Arr_Dep == undefined)
            trHTML += `<font class='time-deprecated'>00:00 AM</font>` + ' | ' + `<font class='time-deprecated'>00:00 AM</font>`
        else {
            if (time_Arr_Dep[0] == "")
                trHTML += `<font class='time-deprecated'>00:00 AM</font>`
            else trHTML += `<font class='time-arrival'>${convert12hour(time_Arr_Dep[0].substring(0, 5))}</font>`
            trHTML += ' | '
            if (time_Arr_Dep[1] == "")
                trHTML += `<font class='time-deprecated'>00:00 AM</font>`
            else trHTML += `<font class='time-departure'>${convert12hour(time_Arr_Dep[1].substring(0, 5))}</font>`
        }
        trHTML += '</td>'
    }
    tr.html(trHTML)

    var temp = 0
    var passedTravelActivities = new Array()

    tr = $(".travel-mode-row").first()
    trHTML = `<td class='suggestion strong'>Travel mode</td>`
    for (i = 0; i < suggestions[index].activities.length - 1; i++) {
        var activity = suggestions[index].activities[i]
        var activity_next = suggestions[index].activities[i + 1]
        var mode = ""
        if (activity.includes("<font color=") && activity_next.includes("<font color=")) {
            mode = suggestions[index].mode
            if (temp == 0) temp = i
        }
        else {
            for (var j = 0; j < travelActivities.length; j ++)
                if ( (passedTravelActivities["" + j] == undefined || passedTravelActivities["" + j] != "passed") &&
                     travelActivities[j].purpose.includes(activity_next.replace("<font color='red'>", "").replace("</font>", "")) ){
                    passedTravelActivities["" + j] = "passed"
                    mode = travelActivities[j].travelMode
                    break
                }
        }
        trHTML += `<td class='suggestion'><label>${mode}</label></td>`
    }
    tr.html(trHTML)

    tr = $(".location-row").first()
    trHTML = "<td class='suggestion strong'>Nearby location</td>"
    for (i = 0; i < temp; i++)
        trHTML += "<td class='suggestion'></td>"
    trHTML += `<td class='suggestion' colspan='3'>${suggestions[index].nearbyLocation}</td>`
    tr.html(trHTML)
}

function toNextSuggestion() {
    if ($("#option-choice-yes").prop("checked"))
        selectedSuggestions.push(index)

    index++
    if (index >= suggestions.length) {
        alert("Here's the end of suggestions !")

        var suggestionsToSave = []
        for (var i = 0; i < suggestions.length; i ++) {
            if (selectedSuggestions.includes(i))
                suggestions[i].accepted_by_user = true
            else suggestions[i].accepted_by_user = false
            suggestionsToSave.push(suggestions[i])
            console.log(suggestions[i])
        }

        $("#suggestions_to_save").val(JSON.stringify(suggestionsToSave))
        var form = document.getElementById("form_suggestions_save")
        $.ajax({
            type: 'post',
            url: form.action,
            data: $(form).serialize(),
            success: function() {
                location.href = urlForStep5
            },
            error: function(error) {
                alert(`Error ${error}`)
            }
        })
    } else updateView()
}

function convert12hour(strTime) {
    var hour = parseInt(strTime.substring(0, 2))
    if (hour > 12)
        return `${hour - 12}:${strTime.substring(3, 5)} PM`
    else if(hour == 12)
        return `${strTime} PM`
    else return `${strTime} AM`
}