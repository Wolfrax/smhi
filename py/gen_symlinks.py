import os

# Set the directory you want to start from
root = 'metobs_data'
dirs = []
for dirName, subdirList, fileList in os.walk(root):
    if fileList and dirName != root and dirName.find('img') < 0:
        dirs.append(dirName)

dirs = sorted(dirs)

for dir in dirs:
    try:
        os.symlink(latest_path, os.path.join(ROOT, 'latest'))
    except FileExistsError:
        os.remove(os.path.join(ROOT, 'latest'))
        os.symlink(latest_path, os.path.join(ROOT, 'latest'))

    print('Found directory: %s' % dir)
