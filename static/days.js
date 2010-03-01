/* Determines maximum days in month */

function daysInMonth(month,year) {
    var m = [31,28,31,30,31,30,31,31,30,31,30,31];
    if (month != 2) return m[month - 1];
    if (year%4 != 0) return m[1];
    if (year%100 == 0 && year%400 != 0) return m[1];
    return m[1] + 1;
}

function getDays() {
    var day = document.getElementById('day').value
    var month = document.getElementById('month').value;
    var year = document.getElementById('year').value;
    var maxDays = daysInMonth(month, year);
    var dayList = document.getElementById('day');
    
    dayList.options.length = 0
    
    if (maxDays == dayList.options.length)
    {
        return
    }

    for (i=1;i<=maxDays;i++)
    { 
        dayList.options[dayList.options.length] = new Option(i,i); 
    }

    if (day > maxDays)
    {
        dayList.selectedIndex = maxDays-1;
    }
    else
    {
        dayList.selectedIndex = day-1;
    }
}
