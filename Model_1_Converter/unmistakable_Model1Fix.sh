#!/bin/sh
exec >/dev/console
TLIs="ST3DP1Q,ST3DP1"

#Get current TLI information from karas.db
TLI=`/app/karas_pinetree_util.sh --get-tli`

#Kill normal screen apps
/app/tinydebug wdt disable
kill -9 `pidof stdin2log`
kill -9 `pidof appBrowser`
/app/tinydebug wdt disable

#Display on screen current TLI information
/app/display.sh "Current ID" "$TLI" "Touch to continue"
/app/tinydebug keywait

#Give user chance to cancel if desired
/app/display.sh "Touch screen" "to change ID" "to DP200Q" "or turn off to cancel"
/app/tinydebug keywait

#Set the new TLI if the old one is a Stanley Model 1
for i in `echo ${TLIs} | tr ',' '\n'` ; do
    [ $TLI = ${i} ] && {
        newTLI=3DP200Q
        /app/karas_pinetree_util.sh --set-tli $newTLI
        break;
    }
done

#Check if TLI change was a success
newTLI=`/app/karas_pinetree_util.sh --get-tli`
if [ "$newTLI" = "$TLI" ]; then
    /app/display.sh "TLI is not changed." "Touch screen" "to reboot"
	/app/tinydebug keywait
	/app/karas_pinetree_util.sh --reboot
else 
    /app/display.sh "TLI changed properly" "$newTLI" "Touch screen" "to reboot"
	/app/tinydebug keywait
	/app/karas_pinetree_util.sh --reboot
fi

exit 0
