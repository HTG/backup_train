import boto
import sys
import os
import argparse
import locale

class DefaultHelpParser(argparse.ArgumentParser):
  """
  Provides a wrapper on ArgumentParser that prints help when there's an error
  """
  def error(self, message):
    self.print_help()
    print("====== Error =====")
    print('error: %s\n' % message)
    sys.exit(2)

def throws(msg):
  """generic throws class for messages to reduce typing"""
  raise RuntimeError(msg)

def directory_entry(dir_path,needle):
  """
  Retrieves the directory entires as a list style object, allows the user to specify which item they would like out of the list

  Keyword arguments:
  dir_path -- the path to a directory to list directories
  needle -- the position in the sorted directory list
  """
  dirs = list()
  try:
    for d in os.listdir(dir_path):
      if os.path.isdir(os.path.join(dir_path,d)):
        dirs.append(d)
  except:
    throws("Unable to open %s" % dir_path)

  # sort the list order since it may come back out of order
  dirs_sorted = sorted(dirs,key=str.lower)

  # return the selected entry
  return dirs_sorted[needle]

def debug_print(msg,should_print):
  if should_print == True:
    print(msg)

def execute_command(cmd,is_test_mode):
  return_value = 0
  try:
    if is_test_mode:
      return_value = 0
    else:
      return_value = os.system(cmd)
  except:
    throws("Unable to execute command %s, returned value if we got that far: %d " % (cmd, return_value))
  return return_value

def main():

  parser = DefaultHelpParser(description="Provides details on an innobackupex S3 storage bucket")
  required_args = parser.add_argument_group("required arugments")
  optional_args = parser.add_argument_group("optional arguments")

  required_args.add_argument("-b","--bucket",dest="bucket",required=True,help="the target S3 bucket to work with")
  required_args.add_argument("-d","--directory",dest="directory",required=True,help="the directory where the innobackupex backups will be retrieved to")

  optional_args.add_argument("-r","--restore",dest="restore",required=False,help="attempts to restore from the backups directory specified",default=False,action="store_true")
  optional_args.add_argument("--test",dest="test",help="enable test mode, no operations will actually occur",default=False,action="store_true")
  optional_args.add_argument("--verbose",dest="verbose",help="enable debug printing",default=False,action="store_true")

  args = parser.parse_args()
  # required
  bucket = args.bucket
  directory = args.directory
  # optional
  restore = args.restore
  test_mode = args.test
  verbose = args.verbose

  conn = boto.connect_s3()
  debug_print("bucket name: %s" % bucket, verbose)
  backup_storage = conn.get_bucket(bucket)

  # iterate the items in the bucket, assumed to be innobackupex items
  # 2013-10-26_16-09-39-full/
  # 2013-11-06_21-36-41/
  # 2013-11-08_22-22-31/ etc.
  backups = list()
  for key in backup_storage.list(delimiter="/"):
    backups.append(key.name)

  # sort the backups
  backups_sorted = sorted(backups,cmp=locale.strcoll)
  debug_print(backups_sorted,verbose)

  # find the last full backup
  last_full_backup = ""
  for b in reversed(backups_sorted):
    debug_print("looking for '-FULL' in %s" % b,verbose)
    if "-FULL" in b:
      last_full_backup = b
      break

  if last_full_backup == "":
    throws("Unable to find last full backup")

  debug_print("last backup: %s" % last_full_backup, verbose)

  # retrieve all the backups from the last backup and all the incrementals
  f = backups_sorted.index(last_full_backup)
  incremental_backups = list()
  for i in range(f,len(backups_sorted)):
    debug_print("Adding %s to list of items to get" % backups_sorted[i],verbose)
    incremental_backups.append(backups_sorted[i])

  # fetch all the backups listed
  for i in incremental_backups:
    base_cmd = "aws s3 cp s3://%s/%s %s --recursive"
    retrieve_cmd = base_cmd % (bucket,i,os.path.join(directory,i))
    debug_print("exec: %s" % retrieve_cmd,verbose)
    return_value = execute_command(retrieve_cmd,test_mode)

  if restore:
    restore_cmd = "innobackupex --copy-back %s" % directory
    debug_print("restore: %s" % restore_cmd,verbose)
    return_value = execute_command(restore_cmd,test_mode)


if __name__ == "__main__":
  main()
