import argparse
import json
import urllib.request
import urllib.parse
import os
import shutil
import uuid

from datetime import datetime
from getpass import getpass
from stream_zip import stream_zip, ZIP_64


def is_uuid(string):
    try:
        uuid.UUID(string)
        return True
    except ValueError:
        return False

def is_bag(path):
    return is_uuid(path.split('/')[-1]) and 'metadata.yaml' in os.listdir(path)

def refresh_access(refresh):
    data = urllib.parse.urlencode({ "refresh": refresh }).encode()
    req =  urllib.request.Request("https://api.woeden.com/auth/refresh/", data=data)
    resp = urllib.request.urlopen(req)
    resp = json.loads(resp.read())
    return resp['access']

def upload_bag(bag_uuid, dir, access):
    data = urllib.parse.urlencode({ 'manual': True }).encode()
    req =  urllib.request.Request(f"https://api.woeden.com/bag/{bag_uuid}/upload/", data=data)
    req.add_header('Authorization', f'Bearer {access}')
    resp = urllib.request.urlopen(req)
    urls = json.loads(resp.read())['urls']

    def unzipped_files():
        modified_at = datetime.now()
        perms = 0o600

        def get_bytes(file):
            with open(f'{dir}/{file}', 'rb') as f:
                data = f.read(1073741824)
                while data:
                    yield data
                    data = f.read(1073741824)

        for file in os.listdir(dir):
            yield file, modified_at, perms, ZIP_64, get_bytes(file)
    
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
    data = urllib.parse.urlencode({ "parts": json.dumps(parts) }).encode()
    req =  urllib.request.Request(f"https://api.woeden.com/bag/{bag_uuid}/uploaded/", data=data)
    req.add_header('Authorization', f'Bearer {access}')
    urllib.request.urlopen(req)

parser = argparse.ArgumentParser(description='Upload bags to Woeden')
parser.add_argument('dir', type=str, help="Mount path of external storage device")
parser.add_argument('--email', type=str, help='Account email')
args = parser.parse_args()

print("""
██     ██  ██████  ███████ ██████  ███████ ███    ██ 
██     ██ ██    ██ ██      ██   ██ ██      ████   ██ 
██  █  ██ ██    ██ █████   ██   ██ █████   ██ ██  ██ 
██ ███ ██ ██    ██ ██      ██   ██ ██      ██  ██ ██ 
 ███ ███   ██████  ███████ ██████  ███████ ██   ████ 
                                                                                                     
""")

print("Let's upload some bags.")

email = args.email if args.email is not None else input("Email: ")
password = getpass()

print("Logging in...")

data = urllib.parse.urlencode({ "username": email, "password": password }).encode()
req =  urllib.request.Request("https://api.woeden.com/auth/login/", data=data)
resp = urllib.request.urlopen(req)
resp = json.loads(resp.read())

print("Successfully logged in.\n")

ACCESS = resp['access']
REFRESH = resp['refresh']

print("Searching for bags that have not been uploaded...")

bag_paths = {}
paths_to_search = [args.dir, f'{args.dir}/woeden', f'{args.dir}/woeden/bags']
for path in paths_to_search:
    for dir in os.listdir(path):
        if is_bag(f'{path}/{dir}'):
            bag_paths[dir] = f'{path}/{dir}'
    if len(bag_paths) > 0:
        break

if len(bag_paths.keys()) == 0:
    print("Could not find bags. Please verify the device is mounted at the specified directory.")
    exit()

bags_req =  urllib.request.Request("https://api.woeden.com/bag/")
bags_req.add_header('Authorization', f'Bearer {ACCESS}')
bags_resp = urllib.request.urlopen(bags_req)
bags_to_upload = {}
for bag in json.loads(bags_resp.read()):
    if bag['upload_status'] == 'NOT_UPLOADED' and bag['bag_uuid'] in bag_paths:
        bags_to_upload[bag['bag_uuid']] = bag
        bags_to_upload[bag['bag_uuid']]['path'] = bag_paths[bag['bag_uuid']]

if len(bags_to_upload.keys()) == 0:
    print("No bags to upload.")
    exit()

print("The following bags have not been uploaded:")
for bag_uuid in bags_to_upload.keys():
    print("  - " + bags_to_upload[bag_uuid]['name'])
upload_all = input("Do you wish to upload them all? (y/n): ")

if upload_all not in ('y', 'n'):
    print("Please enter a valid response.")
    exit()

if upload_all == 'n':
    keys = list(bags_to_upload.keys())
    for bag_uuid in keys:
        upload = input(f"Upload {bags_to_upload[bag_uuid]['name']}? (y/n): ")
        if upload not in ('y', 'n'):
            print("Please enter a valid response.")
            exit()
        if upload == 'n':
            del bags_to_upload[bag_uuid]

bag_uuids = list(bags_to_upload.keys())
for i in range(len(bag_uuids)):
    bag = bags_to_upload[bag_uuids[i]]
    bag_uuid = bag['bag_uuid']
    path = bag['path']
    try:
        parts = upload_bag(bag_uuid, path, ACCESS)
        mark_uploaded(bag_uuid, parts, ACCESS)
    except:
        ACCESS = refresh_access(REFRESH)
        parts = upload_bag(bag_uuid, path, ACCESS)
        mark_uploaded(bag_uuid, parts, ACCESS)
    print(f"Uploaded {i+1}/{len(bag_uuids)}: {bag['name']}")
