#!/usr/bin/env python
import os
import json
import logging
import argparse
import socket
from threading import Timer
import subprocess

#from bottle import Bottle, run, template, static_file, request, response
#BaseRequest, default_app
from flask import Flask, current_app, request, render_template, jsonify, make_response

from indi_server import IndiServer, INDI_PORT, INDI_FIFO, INDI_CONFIG_DIR
from driver import DeviceDriver, DriverCollection, INDI_DATA_DIR
from database import Database
from device import Device

# default settings
WEB_HOST = '0.0.0.0'
WEB_PORT = 8624


parser = argparse.ArgumentParser(
    description='INDI Web Manager. '
    'A simple web application to manage an INDI server')

parser.add_argument('--indi-port', '-p', type=int, default=INDI_PORT,
                    help='indiserver port (default: %d)' % INDI_PORT)
parser.add_argument('--port', '-P', type=int, default=WEB_PORT,
                    help='Web server port (default: %d)' % WEB_PORT)
parser.add_argument('--host', '-H', default=WEB_HOST,
                    help='Bind web server to this interface (default: %s)' %
                    WEB_HOST)
parser.add_argument('--fifo', '-f', default=INDI_FIFO,
                    help='indiserver FIFO path (default: %s)' % INDI_FIFO)
parser.add_argument('--conf', '-c', default=INDI_CONFIG_DIR,
                    help='INDI config. directory (default: %s)' % INDI_CONFIG_DIR)
parser.add_argument('--xmldir', '-x', default=INDI_DATA_DIR,
                    help='INDI XML directory (default: %s)' % INDI_DATA_DIR)
parser.add_argument('--verbose', '-v', action='store_true',
                    help='Print more messages')
parser.add_argument('--logfile', '-l', help='log file name')
parser.add_argument('--server', '-s', default='standalone',
                    help='HTTP server [standalone|apache] (default: standalone')

args = parser.parse_args()


logging_level = logging.WARNING

if args.verbose:
    logging_level = logging.DEBUG

if args.logfile:
    logging.basicConfig(filename=args.logfile,
                        format='%(asctime)s - %(levelname)s: %(message)s',
                        level=logging_level)

else:
    logging.basicConfig(format='%(asctime)s - %(levelname)s: %(message)s',
                        level=logging_level)

logging.debug("command line arguments: " + str(vars(args)))

collection = DriverCollection(args.xmldir)
indi_server = IndiServer(args.fifo, args.conf)
indi_device = Device()

db_path = os.path.join(args.conf, 'profiles.db')
db = Database(db_path)

collection.parse_custom_drivers(db.get_custom_drivers())


def __mian__(args):
    pass



app = Flask(__name__)
logging.info('using Bottle as standalone server')


saved_profile = None
active_profile = ""


def start_profile(profile):
    info = db.get_profile(profile)

    profile_drivers = db.get_profile_drivers_labels(profile)
    all_drivers = [collection.by_label(d['label']) for d in profile_drivers]
    indi_server.start(info['port'], all_drivers)
        # Auto connect drivers in 3 seconds if required.
    if info['autoconnect'] == 1:
        t = Timer(3, indi_server.auto_connect)
        t.start()

@app.route('/favicon.ico', methods=['GET'])
def get_favicon():
    """Serve favicon"""
    return current_app.send_static_file('favicon.ico')

@app.route('/')
def main_form():
    """Main page"""
    global saved_profile
    drivers = collection.get_families()

    if not saved_profile:
        saved_profile = request.cookies.get('indiserver_profile') or 'Simulators'

    profiles = db.get_profiles()
    hostname = socket.gethostname()
    return render_template('form.html', profiles=profiles,
                    drivers=drivers, saved_profile=saved_profile,
                    hostname=hostname)

###############################################################################
# Profile endpoints
###############################################################################


@app.route('/api/profiles', methods=['GET'])
def get_json_profiles():
    """Get all profiles (JSON)"""
    results = db.get_profiles()
    return json.dumps(results)
   
@app.route('/api/profiles/<item>', methods=['GET'])
def get_json_profile(item):
    """Get one profile info"""
    results = db.get_profile(item)
    return json.dumps(results)

@app.route('/api/profiles/<name>', methods=['POST'])
def add_profile(name):
    """Add new profile"""
    db.add_profile(name)
    return ''

@app.route('/api/profiles/<name>', methods=['DELETE'])
def delete_profile(name):
    """Delete Profile"""
    db.delete_profile(name)
    return ''

@app.route('/api/profiles/<name>', methods=['PUT'])
def update_profile(name):
    """Update profile info (port & autostart & autoconnect)"""
    resp = make_response("set cookie")
    resp.set_cookie("indiserver_profile", name, path='/')
    data = request.json
    port = data.get('port', args.indi_port)
    autostart = bool(data.get('autostart', 0))
    autoconnect = bool(data.get('autoconnect', 0))
    db.update_profile(name, port, autostart, autoconnect)
    return ''

@app.route('/api/profiles/<name>/drivers', methods=['POST'])
def save_profile_drivers(name):
    """Add drivers to existing profile"""
    data = request.json
    db.save_profile_drivers(name, data)
    return ''


@app.route('/api/profiles/custom', methods=['POST'])
def save_profile_custom_driver():
    """Add custom driver to existing profile"""
    data = request.json(silent=False)
    db.save_profile_custom_driver(data)
    collection.clear_custom_drivers()
    collection.parse_custom_drivers(db.get_custom_drivers())


@app.route('/api/profiles/<item>/labels', methods=['GET'])
def get_json_profile_labels(item):
    """Get driver labels of specific profile"""
    results = db.get_profile_drivers_labels(item)
    return json.dumps(results)


@app.route('/api/profiles/<item>/remote', methods=['GET'])
def get_remote_drivers(item):
    """Get remote drivers of specific profile"""
    results = db.get_profile_remote_drivers(item)
    if results is None:
        results = {}
    return json.dumps(results)


###############################################################################
# Server endpoints
###############################################################################

@app.route('/api/server/status', methods=['GET'])
def get_server_status():
    """Server status"""
    status = [{'status': str(indi_server.is_running()), 'active_profile': active_profile}]
    return json.dumps(status)


@app.route('/api/server/drivers', methods=['GET'])
def get_server_drivers():
    """List server drivers"""
    # status = []
    # for driver in indi_server.get_running_drivers():
    #     status.append({'driver': driver})
    # return json.dumps(status)
    # labels = []
    # for label in sorted(indi_server.get_running_drivers().keys()):
    #     labels.append({'driver': label})
    # return json.dumps(labels)
    drivers = []
    if indi_server.is_running() is True:
        for driver in indi_server.get_running_drivers().values():
            drivers.append(driver.__dict__)
    return json.dumps(drivers)


@app.route('/api/server/start/<profile>', methods=['POST'])
def start_server(profile):
    """Start INDI server for a specific profile"""
    global saved_profile
    saved_profile = profile
    global active_profile
    active_profile = profile
    res = make_response()
    res.set_cookie("indiserver_profile", profile)
    start_profile(profile)
    return ''


@app.route('/api/server/stop', methods=['POST'])
def stop_server():
    """Stop INDI Server"""
    indi_server.stop()

    global active_profile
    active_profile = ""

    # If there is saved_profile already let's try to reset it
    global saved_profile
    if saved_profile:
        saved_profile = request.cookies.get("indiserver_profile") or "Simulators"
    return ''


###############################################################################
# Driver endpoints
###############################################################################

@app.route('/api/drivers/groups', methods=['GET'])
def get_json_groups():
    """Get all driver families (JSON)"""
    response.content_type = 'application/json'
    families = collection.get_families()
    return json.dumps(sorted(families.keys()))


@app.route('/api/drivers', methods=['GET'])
def get_json_drivers():
    """Get all drivers (JSON)"""
    response.content_type = 'application/json'
    return json.dumps([ob.__dict__ for ob in collection.drivers])


@app.route('/api/drivers/start/<label>', methods=['POST'])
def start_driver(label):
    """Start INDI driver"""
    driver = collection.by_label(label)
    indi_server.start_driver(driver)
    logging.info('Driver "%s" started.' % label)
    return ''



@app.route('/api/drivers/stop/<label>', methods=['POST'])
def stop_driver(label):
    """Stop INDI driver"""
    driver = collection.by_label(label)
    indi_server.stop_driver(driver)
    logging.info('Driver "%s" stopped.' % label)
    return ''


@app.route('/api/drivers/restart/<label>', methods=['POST'])
def restart_driver(label):
    """Restart INDI driver"""
    driver = collection.by_label(label)
    indi_server.stop_driver(driver)
    indi_server.start_driver(driver)
    logging.info('Driver "%s" restarted.' % label)
    return ''

###############################################################################
# Device endpoints
###############################################################################


@app.route('/api/devices', methods=['GET'])
def get_devices():
    return json.dumps(indi_device.get_devices())

###############################################################################
# System control endpoints
###############################################################################


@app.route('/api/system/reboot', methods=['POST'])
def system_reboot():
    """reboot the system running indi-web"""
    logging.info('System reboot, stopping server...')
    stop_server()
    logging.info('rebooting...')
    subprocess.call('reboot')


@app.route('/api/system/poweroff', methods=['POST'])
def system_poweroff():
    """poweroff the system"""
    logging.info('System poweroff, stopping server...')
    stop_server()
    logging.info('poweroff...')
    subprocess.run("poweroff")

###############################################################################
# Startup standalone server
###############################################################################


def main():
    """Start autostart profile if any"""
    global active_profile

    for profile in db.get_profiles():
        if profile['autostart']:
            start_profile(profile['name'])
            active_profile = profile['name']
            break

    logging.info("Exiting")


# JM 2018-12-24: Added __main__ so I can debug this as a module in PyCharm
# Otherwise, I couldn't get it to run main as all

if __name__ == '__main__':
    app.jinja_env.auto_reload = True
    main()
    app.run(host=args.host, port=args.port, debug=True, threaded=True)