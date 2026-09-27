cd imu-viewer
npm run build
mpremote connect COM8 fs cp -r ./dist :
cd ../main
mpremote connect COM8 fs cp -r ./lib :
mpremote connect COM8 fs cp ./main.py :
mpremote connect COM8 fs cp ./imu_server.py :
