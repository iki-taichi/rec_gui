# rec_gui
An Environment for Recording Low-Level Manipulations in Graphical User Interfaces

<img src="docs/overview_rec_gui.jpg" width="700"/>

## Usage

Here, we describe the usage of RecGUI running in the local host.

### - Recording

#### Build the image

```
cd rec_gui
docker build -t rec_gui .
```

#### Run the rec_gui container

```
docker run -p 5900:5900 -p 5902:5902 -p 8888:8888 --mount type=bind,source=$(pwd)/files,target=/files -v /dev/shm:/dev/shm  --network bridge --init --name rec_gui rec_gui
```

We use the 5902 port to access to the VNC server through proxy, the 8888 port to access to web ui.
The 5900 port is optional, which provide a direct access to the VNC server to see the display manipulated by another user.

Once you run the image, you can use the start command to reboot the container.

```
docker start -a rec_gui
```

#### Record a GUI manipulation.

Access port 5902 with your VNC Client. We used the VNC viewer provided by RealVNC in our dev environment.

You will be asked to enter a passward. The default password is "vnc" (hard coded in supervisord.conf).
After entering the passward, you will be navigated to the welcome page.
Push the start button to start a task sequence and the recoring.


### - Converting

We use the web UI to convert the recorded data (images and manipulation log) into image-action sequences for the model training.

Access the web UI with your browser by entering the url http://localhost:8888/webui/index .
The page will present some links for the functions of this web UI.

We can see the list of records in the Records page and convert each record by pushing the convert button.

Converted data will be storaged in the files/converted/\<TIMESTAMP\> directory.
The directory includes a series of images and a json file that contains the list of the output actions in every time intervals:

```
+ <TIMESTAMP>
    - meta.json
    - 0.jpg
    - 1.jpg
    ...
```

### - Define task sequences

ToDo

