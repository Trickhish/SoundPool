#!/usr/bin/env bash
# Build the Angular app for production and deploy it to the soundpool.dury.dev
# web root served by Apache.
set -e
cd "$(dirname "$0")"
./node_modules/.bin/ng build --configuration production
rm -rf /var/www/soundpool/*
cp -r dist/soundpool/browser/. /var/www/soundpool/
chown -R www-data:www-data /var/www/soundpool
chmod -R a+rX /var/www/soundpool
echo "Deployed to /var/www/soundpool (https://soundpool.dury.dev)"
