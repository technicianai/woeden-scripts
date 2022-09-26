import argparse
import getpass
import json
import os
import urllib.request
import urllib.parse
import uuid
import yaml

from datetime import datetime
from getpass import getpass
from stream_zip import stream_zip, ZIP_64


HOST = 'https://api.woeden.com'

def fetch_tokens(email, password):
    data = urllib.parse.urlencode({ 'username': email, 'password': password }).encode()
    req =  urllib.request.Request(f'{HOST}/auth/login/', data=data)
    resp = urllib.request.urlopen(req)
    resp = json.loads(resp.read())
    return resp

def refresh_access(refresh):
    data = urllib.parse.urlencode({ 'refresh': refresh }).encode()
    req =  urllib.request.Request(f'{HOST}/auth/refresh/', data=data)
    resp = urllib.request.urlopen(req)
    resp = json.loads(resp.read())
    return resp['access']

def fetch_robots(access):
    req =  urllib.request.Request(f'{HOST}/robot/')
    req.add_header('Authorization', f'Bearer {access}')
    resp = urllib.request.urlopen(req)
    resp = json.loads(resp.read())
    return resp

def fetch_bags(access):
    req =  urllib.request.Request(f'{HOST}/bag/')
    req.add_header('Authorization', f'Bearer {access}')
    resp = urllib.request.urlopen(req)
    resp = json.loads(resp.read())
    return resp

def is_bag(path):
    if not os.path.isdir(path):
        return False
    for file in os.listdir(path):
        if not ('.db3' in file or file == 'metadata.yaml'):
            return False
    return True

def register_bag(name, robot_id, path, access):
    bag_uuid = str(uuid.uuid4())

    with open(f'{path}/metadata.yaml', 'r') as stream:
        try:
            metadata = yaml.safe_load(stream)
        except yaml.YAMLError as e:
            print(e)

    to_seconds = lambda ns: int(ns / 1e9)
    start_time = to_seconds(metadata['rosbag2_bagfile_information']['starting_time']['nanoseconds_since_epoch'])
    duration = to_seconds(metadata['rosbag2_bagfile_information']['duration']['nanoseconds'])
    end_time = start_time + duration

    size = sum(os.path.getsize(f'{path}/{f}') for f in os.listdir(path) if os.path.isfile(f'{path}/{f}'))

    topics = []
    for twmc in metadata['rosbag2_bagfile_information']['topics_with_message_count']:
        topics.append({
            'name': twmc['topic_metadata']['name'],
            'type': twmc['topic_metadata']['type'],
            'frequency': 0,
            'max_frequency': False
        })

    data = urllib.parse.urlencode({
        'bag_uuid': bag_uuid,
        'metadata': json.dumps(metadata),
        'size': size,
        'start_time': start_time,
        'end_time': end_time,
        'topics': json.dumps(topics),
        'name': name,
        'robot_id': robot_id
    }).encode()
    req =  urllib.request.Request(f'{HOST}/bag/', data=data)
    req.add_header('Authorization', f'Bearer {access}')
    urllib.request.urlopen(req)

    return bag_uuid

def upload_bag(bag_uuid, path, access):
    data = urllib.parse.urlencode({ 'manual': True }).encode()
    req =  urllib.request.Request(f'{HOST}/bag/{bag_uuid}/upload/', data=data)
    req.add_header('Authorization', f'Bearer {access}')
    resp = urllib.request.urlopen(req)
    urls = json.loads(resp.read())['urls']

    def unzipped_files():
        modified_at = datetime.now()
        perms = 0o600

        def get_bytes(file):
            with open(file, 'rb') as f:
                data = f.read(1073741824)
                while data:
                    yield data
                    data = f.read(1073741824)

        for file in os.listdir(path):
            yield file, modified_at, perms, ZIP_64, get_bytes(f'{path}/{file}')
    
    parts = []

    def upload_chunk(gb_chunk, part_no):
        req = urllib.request.Request(url=urls.pop(0), data=gb_chunk, method='PUT')
        res = urllib.request.urlopen(req)
        etag = res.getheader('ETag').replace('"', '')
        parts.append({'ETag': etag, 'PartNumber': part_no})

    i = 1
    chunks = stream_zip(unzipped_files())

    # Upload 1 GB at a time
    chunk = next(chunks)
    gb_chunk = bytearray()
    while chunk:
        if len(gb_chunk) + len(chunk) >= 1073741824:
            upload_chunk(gb_chunk, i)
            i += 1
            gb_chunk = bytearray(chunk)
        else:
            gb_chunk.extend(chunk)
        try:
            chunk = next(chunks)
        except StopIteration:
            break
    
    upload_chunk(gb_chunk, i)

    return parts

def mark_uploaded(bag_uuid, parts, access):
    data = urllib.parse.urlencode({ 'parts': json.dumps(parts) }).encode()
    req =  urllib.request.Request(f'{HOST}/bag/{bag_uuid}/uploaded/', data=data)
    req.add_header('Authorization', f'Bearer {access}')
    urllib.request.urlopen(req)

parser = argparse.ArgumentParser(description='Import bags recorded outside the Woeden ecosystem.')
parser.add_argument('dir', type=str, help='Path to directory containing bags')
parser.add_argument('--email', type=str, help='Account email')
args = parser.parse_args()

print("""
██     ██  ██████  ███████ ██████  ███████ ███    ██ 
██     ██ ██    ██ ██      ██   ██ ██      ████   ██ 
██  █  ██ ██    ██ █████   ██   ██ █████   ██ ██  ██ 
██ ███ ██ ██    ██ ██      ██   ██ ██      ██  ██ ██ 
 ███ ███   ██████  ███████ ██████  ███████ ██   ████ 
                                                                                                     
""")

print('Let\'s import some bags that you recorded without Woeden.')

email = args.email if args.email is not None else input('Email: ')
password = getpass()

print('Logging in...')

try:
    tokens = fetch_tokens(email, password)
except:
    print('User not found for provided credentials. Please try again.')
    exit()

ACCESS = tokens['access']
REFRESH = tokens['refresh']

print('Successfully logged in.\n')

upload_all = input('Do you wish to upload all currently un-registered bags? (y/n): ')
while upload_all not in ('y', 'n'):
    upload_all = input('Please enter a valid response (y/n): ')
upload_all = upload_all == 'y'
print()

robots = fetch_robots(ACCESS)
robot_id_set = set()
for robot in robots:
    id = robot['id']
    robot_id_set.add(id)
    print(f"  - {robot['name']} (id={id})")
robot_id = input('Which robot were these bags recorded on? (id): ')
while not robot_id.isdigit() or int(robot_id) not in robot_id_set:
    robot_id = input('Please enter a valid response (id): ')
robot_id = int(robot_id)

print('\nSearching for bags that have not been registered in Woeden...')

existing_bags = [bag['bag_uuid'] for bag in fetch_bags(ACCESS)]

unregistered_bags = []
for dir in os.listdir(args.dir):
    path = f'{args.dir}/{dir}'
    if is_bag(path) and dir not in existing_bags:
        unregistered_bags.append({
            'name': dir,
            'path': path
        })

if len(unregistered_bags) == 0:
    print(f'No unregistered bags found in directory {args.dir}. Exiting.')
    exit()

print('Found the following bags to import into Woeden: ')
for bag in unregistered_bags:
    print("  - " + bag['name'])
print()

for i in range(len(unregistered_bags)):
    bag = unregistered_bags[i]
    name = bag['name']
    path = bag['path']

    bag_uuid = register_bag(name, robot_id, path, ACCESS)

    if not upload_all:
        upload = input(f'Upload {name}? (y/n): ')
        while upload not in ('y', 'n'):
            upload = input('Please enter a valid response (y/n): ')
        if upload == 'n':
            continue

    try:
        parts = upload_bag(bag_uuid, path, ACCESS)
        mark_uploaded(bag_uuid, parts, ACCESS)
    except:
        ACCESS = refresh_access(REFRESH)
        parts = upload_bag(bag_uuid, path, ACCESS)
        mark_uploaded(bag_uuid, parts, ACCESS)

    print(f'Uploaded {i+1}/{len(unregistered_bags)}: {name}')
