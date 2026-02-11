#!/bin/bash
ENV_FILE=".env"

generate_secret() {
    openssl rand -base64 24 | tr -d '/+='
}

# Only randomize if the placeholders haven't been filled yet
if grep -q "REPLACE_ME" "$ENV_FILE"; then
    echo "Randomizing internal passwords..."
    sed -i "s|DB_PASSWORD=REPLACE_ME|DB_PASSWORD=$(generate_secret)|g" "$ENV_FILE"
    sed -i "s|KC_ADMIN_PASSWORD=REPLACE_ME|KC_ADMIN_PASSWORD=$(generate_secret)|g" "$ENV_FILE"
    echo "Passwords updated in .env."
fi