#!/usr/bin/env bash
# leap-second-probe.sh: what do common runtimes do with 2016-12-31T23:59:60Z?
# Runs whichever of python3/python, node, go, java, gcc, powershell.exe and GNU date it finds.
# Note: on a freshly booted Linux machine the kernel TAI offset can read 0 for a few
# seconds before a time daemon sets it to 37, so the CLOCK_TAI line may vary.
# Needs curl for the IANA leap-second count. Writes temp files to a scratch directory.
set -u
D=$(mktemp -d); cd "$D" || exit 1

echo "== IANA leap-seconds.list =="
if curl -fsSL https://data.iana.org/time-zones/tzdb/leap-seconds.list -o ls.list; then
  grep -v '^#' ls.list | awk 'NF{n++; last=$0} END{printf "entries: %d (first is the 1972 base offset), leap seconds: %d\nlast entry: %s\n", n, n-1, last}'
fi

PY=$(command -v python3 || command -v python)
if [ -n "${PY:-}" ]; then
cat > t.py <<'E'
import datetime, time, calendar
def tryit(label, f):
    try: print(f"python   {label}: {f()}")
    except Exception as e: print(f"python   {label}: ERROR {type(e).__name__}: {e}")
tryit("datetime(2016,12,31,23,59,60)", lambda: datetime.datetime(2016,12,31,23,59,60))
tryit("fromisoformat(..T23:59:60Z)", lambda: datetime.datetime.fromisoformat("2016-12-31T23:59:60+00:00"))
def strp():
    t=time.strptime("2016-12-31 23:59:60","%Y-%m-%d %H:%M:%S"); return f"accepted tm_sec={t.tm_sec}, timegm={calendar.timegm(t)}"
tryit("time.strptime(23:59:60)", strp)
u=lambda *a: calendar.timegm(datetime.datetime(*a).timetuple())
print("python   diff 2017-01-01T00:00:00 - 2016-12-31T23:59:59 =", u(2017,1,1,0,0,0)-u(2016,12,31,23,59,59), "s")
print("python   seconds in 2016 =", u(2017,1,1)-u(2016,1,1))
E
echo "== python =="; "$PY" t.py
fi

if command -v node >/dev/null; then
cat > t.js <<'E'
const t=(l,f)=>{try{console.log(`node     ${l}: ${f()}`)}catch(e){console.log(`node     ${l}: ERROR ${e.name}: ${e.message}`)}};
t('new Date("2016-12-31T23:59:60Z")',()=>{const d=new Date("2016-12-31T23:59:60Z");return isNaN(d)?"Invalid Date":d.toISOString()});
t('Date.UTC(2016,11,31,23,59,60)',()=>{const v=Date.UTC(2016,11,31,23,59,60);return `${v/1000} -> ${new Date(v).toISOString()}`});
const u=(...a)=>Date.UTC(...a)/1000;
console.log("node     diff 2017-01-01T00:00:00 - 2016-12-31T23:59:59 =",u(2017,0,1,0,0,0)-u(2016,11,31,23,59,59),"s");
console.log("node     seconds in 2016 =",u(2017,0,1)-u(2016,0,1));
E
echo "== node =="; node t.js
fi

if command -v go >/dev/null; then
cat > t.go <<'E'
package main
import ("fmt";"time")
func main(){
 _,err:=time.Parse(time.RFC3339,"2016-12-31T23:59:60Z")
 fmt.Println("go       time.Parse(RFC3339, ..23:59:60Z):", func()string{if err!=nil{return "ERROR "+err.Error()};return "accepted"}())
 d:=time.Date(2016,12,31,23,59,60,0,time.UTC)
 fmt.Println("go       time.Date(2016,12,31,23,59,60):", d.Format(time.RFC3339), d.Unix())
 a:=time.Date(2016,12,31,23,59,59,0,time.UTC); b:=time.Date(2017,1,1,0,0,0,0,time.UTC)
 fmt.Printf("go       diff 2017-01-01T00:00:00 - 2016-12-31T23:59:59 = %.0f s\n", b.Sub(a).Seconds())
 fmt.Printf("go       seconds in 2016 = %.0f\n", time.Date(2017,1,1,0,0,0,0,time.UTC).Sub(time.Date(2016,1,1,0,0,0,0,time.UTC)).Seconds())
}
E
echo "== go =="; go run t.go
fi

if command -v java >/dev/null; then
cat > T.java <<'E'
import java.time.*;
public class T {
  interface F { Object run() throws Exception; }
  static void t(String l, F f){ try{ System.out.println("java     "+l+": "+f.run()); }catch(Exception e){ System.out.println("java     "+l+": ERROR "+e.getClass().getSimpleName()+": "+e.getMessage()); } }
  public static void main(String[] a){
    t("LocalDateTime.of(2016,12,31,23,59,60)", () -> LocalDateTime.of(2016,12,31,23,59,60));
    t("OffsetDateTime.parse(..23:59:60Z)", () -> OffsetDateTime.parse("2016-12-31T23:59:60Z"));
    t("Instant.parse(..23:59:60Z)", () -> { Instant i=Instant.parse("2016-12-31T23:59:60Z"); return i+" epoch="+i.getEpochSecond(); });
    Instant x=Instant.parse("2016-12-31T23:59:59Z"), y=Instant.parse("2017-01-01T00:00:00Z");
    System.out.println("java     diff 2017-01-01T00:00:00 - 2016-12-31T23:59:59 = "+Duration.between(x,y).getSeconds()+" s");
    System.out.println("java     seconds in 2016 = "+Duration.between(Instant.parse("2016-01-01T00:00:00Z"),Instant.parse("2017-01-01T00:00:00Z")).getSeconds());
  }
}
E
echo "== java =="; java T.java 2>&1
fi

if command -v gcc >/dev/null; then
cat > t.c <<'E'
#define _GNU_SOURCE
#include <stdio.h>
#include <time.h>
#include <string.h>
int main(void){
  struct tm tm; memset(&tm,0,sizeof tm);
  char *r=strptime("2016-12-31 23:59:60","%Y-%m-%d %H:%M:%S",&tm);
  printf("c        strptime(23:59:60): %s, tm_sec=%d\n", r?"accepted":"REJECTED", tm.tm_sec);
  time_t t=timegm(&tm); printf("c        timegm -> %ld, normalized to %04d-%02d-%02d %02d:%02d:%02d\n",(long)t,tm.tm_year+1900,tm.tm_mon+1,tm.tm_mday,tm.tm_hour,tm.tm_min,tm.tm_sec);
  struct tm a={.tm_year=116,.tm_mon=11,.tm_mday=31,.tm_hour=23,.tm_min=59,.tm_sec=59}, b={.tm_year=117,.tm_mon=0,.tm_mday=1};
  struct tm y0={.tm_year=116,.tm_mon=0,.tm_mday=1}, y1={.tm_year=117,.tm_mon=0,.tm_mday=1};
  printf("c        diff 2017-01-01T00:00:00 - 2016-12-31T23:59:59 = %ld s\n",(long)(timegm(&b)-timegm(&a)));
  printf("c        seconds in 2016 = %ld\n",(long)(timegm(&y1)-timegm(&y0)));
#ifdef CLOCK_TAI
  struct timespec rt,tai; clock_gettime(CLOCK_REALTIME,&rt); clock_gettime(CLOCK_TAI,&tai);
  printf("c        CLOCK_TAI - CLOCK_REALTIME = %.6f s (real TAI-UTC is 37 s)\n",(tai.tv_sec-rt.tv_sec)+(tai.tv_nsec-rt.tv_nsec)/1e9);
#endif
  return 0;}
E
echo "== c =="; gcc -o tc t.c && ./tc
fi

if command -v powershell.exe >/dev/null && ! grep -qi microsoft /proc/version 2>/dev/null; then
cat > t.ps1 <<'E'
function T($l,[scriptblock]$f){ try{ "powershell {0}: {1}" -f $l,(& $f) }catch{ "powershell {0}: ERROR {1}" -f $l,$_.Exception.GetBaseException().GetType().Name } }
T 'DateTime(2016,12,31,23,59,60)' { [datetime]::new(2016,12,31,23,59,60).ToString('o') }
T 'DateTime.Parse(..23:59:60Z)' { [datetime]::Parse('2016-12-31T23:59:60Z').ToString('o') }
T 'DateTimeOffset.Parse(..23:59:60Z)' { [datetimeoffset]::Parse('2016-12-31T23:59:60Z').ToString('o') }
$a=[datetime]::new(2016,12,31,23,59,59,[DateTimeKind]::Utc); $b=[datetime]::new(2017,1,1,0,0,0,[DateTimeKind]::Utc)
"powershell diff 2017-01-01T00:00:00 - 2016-12-31T23:59:59 = {0} s" -f ($b-$a).TotalSeconds
"powershell seconds in 2016 = {0}" -f ([datetime]::new(2017,1,1,0,0,0,[DateTimeKind]::Utc)-[datetime]::new(2016,1,1,0,0,0,[DateTimeKind]::Utc)).TotalSeconds
E
echo "== powershell (Windows PowerShell 5.1 / .NET Framework) =="; powershell.exe -NoProfile -File "$(cygpath -w "$D/t.ps1" 2>/dev/null || echo t.ps1)"
fi

if date --version 2>/dev/null | grep -q GNU; then
  echo "== GNU date =="
  date -u -d '2016-12-31 23:59:60' +%s 2>&1
  echo "diff = $(( $(date -u -d '2017-01-01 00:00:00' +%s) - $(date -u -d '2016-12-31 23:59:59' +%s) )) s"
fi
rm -rf "$D"
