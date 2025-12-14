#!/bin/sh

PATH=/usr/local/ssl/bin/:$PATH
KEY=`cat /app/crypto_key.dat | openssl des3 -d -k "" | tar -xjO`
tar -cvjf- unmistakable_Model1Fix.sh | openssl des3 -e -k $KEY > unmistakable_Model1Fix.she
sync;sync
