#!/bin/sh
# fetch every test file from the PC and check its exact size (sizes.txt)
cd /root
python3 -c "import urllib.request as u; open('sizes.txt','wb').write(u.urlopen('http://10.10.0.85:8099/deploy/sizes.txt').read())"
ok=0; bad=0
while read f n; do
	python3 -c "import urllib.request as u,sys; open(sys.argv[1],'wb').write(u.urlopen('http://10.10.0.85:8099/deploy/'+sys.argv[1]).read())" $f
	if [ "$(wc -c < $f)" = "$n" ]; then ok=$((ok+1)); else bad=$((bad+1)); echo "FETCH BAD $f $(wc -c < $f) want $n"; fi
done < sizes.txt
echo "FETCH ok $ok bad $bad"
