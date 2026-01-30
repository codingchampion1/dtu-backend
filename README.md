# DTU-Backend
This github is for a backend server, it's designed to do a few key functions:
* Host Duty Cards and Signaller Positions: The code is designed to allow hosting of minimized JSON data (to prevent any issues if too many people use the bot) to remember relevevant info.
* Get info from the Public WebSocket: As the name suggests, the code will plug into the public websocket and gather information on Username, TrainData, and Position.
* Calculate distances from Stations: The backend will have a list of server locations hardcoded into the script, which said script will look up info from the WebSocket, and compare the position's distances from the person's Next Station or to calculate the distance between a player and it's Job Site, to automatically boot them off of their Job (Signalling, Dispatching, Et Cetera) if they stray too far.
* Update Duty Card: From Function 1, to update the duty cards whenever someone enters a station.
* Connect with the Front-end: The front end of the discord bot is on fps.ms, and the server's resources are limited. The backend's job is to outsource the complex calculations and storage, and only send (automatically or manually) and recieve data as an API service.

# Contact Me
If the owner(s) of dovedale.wiki, anyone that works for Dovedale Community Discord, or anyone that wants to generally inquire about this code can contact me here:  

GMAIL: fetviper23@gmail.com  

Discord Username: @fetviper
