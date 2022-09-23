# rec_gui
An Environment for Recording Low-Level Manipulations in Graphical User Interfaces

## How to record GUI manipulations

### Run the rec_gui container

```
# build is needed just at the first time.
docker build -t rec_gui .

docker run -p 5900:5900 -p 5902:5902 -p 8888:8888 --mount type=bind,source=$(pwd)/files,target=/files -v /dev/shm:/dev/shm  --network bridge --init --name rec_gui rec_gui
```

### Access port 5902 with your VNC Client

The password is vnc.

You will be navigated to the welcome page.

Push the start button to start a recording and a task sequence.

