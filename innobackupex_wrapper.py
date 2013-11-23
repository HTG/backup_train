#!/usr/bin/python

import os
import argparse
import shutil
import sys

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

  # return the last entry
  return dirs_sorted[needle]

def read_password_from_file(pass_file):
  """
  Reads a 1 line password from the specified file removing '\\n' and '\\r' from the password.
  """
  try:
    f = open(pass_file)
    return f.readline().rstrip("\r\n")
  except:
    throws("Unable to access password file %s " % pass_file)

def debug_print(msg,should_print):
  if should_print == True:
    print(msg)

def exeucte_command(cmd,is_test_mode):
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
  """
  This backup tools performs the following operations based on the arguments provided:

  1. determine the last backup directory, base_backup_dir
  2. backup -->
   - inrcremental: genarate a new backup based on 'base_backup_dir', store in 'new_backup_dir'
   - full: generate a new backup in 'base_backup_dir', store in 'new_backup_dir'
  3. copy 'new_backup_dir' to S3, full backups are postfixed with "<backupname>-full"
  4. remove the oldest backup directory 'oldest_backup_dir'

  """

  parser = DefaultHelpParser(description='Perform backups based on innobackupex')
  required_args = parser.add_argument_group("required arguments")
  optional_args = parser.add_argument_group("optional arguments")

  required_args.add_argument('-d','--directory',required=True,help="""
      innobackupex backup directory to target;
      expects the directories to follow the innobackupex diretory date pattern
      """)
  required_args.add_argument('-p','--password',required=True,help='path to password file')
  required_args.add_argument('-s','--bucket',dest="bucket",required=True,help="the name of the S3 bucket to place the backups in")

  optional_args.add_argument('-b','--backup-type',dest="backup_type",required=False,help="the type of backup to perform; valid options are 'incremental' or 'full', the default is 'incremental'",default="incremental")
  optional_args.add_argument('--no-remove',dest="remove",required=False,help="do not remove the last backup present in the directory",action="store_false",default=True)
  optional_args.add_argument('--test',required=False,help="executes in test mode. no changes are made to the system, only commands are generated",default=False,action="store_true")
  optional_args.add_argument('--verbose',required=False,help="increases verbosity",default=False,action="store_true")

  args = parser.parse_args()

  # get the required items
  backup_directory_path = args.directory
  password_file_path = args.password
  verbosity = args.verbose
  test_mode = args.test
  remove_files = args.remove
  backup_type = args.backup_type
  bucket = args.bucket

  debug_print("Arugments: ",verbosity)
  debug_print(args,verbosity)

  # 1. determine the last backup directory
  base_backup_dir = directory_entry(backup_directory_path,-1)
  debug_print("backup dir: " + base_backup_dir, verbosity)
  password = read_password_from_file(password_file_path)
  debug_print("password: " + password, verbosity)

  ############################
  # 2. Incremental (default) #
  ############################
  if backup_type == "incremental":
    # 2. we get the new directory after we execute the backup by asking for the last directory
    # innobackupex --incremental /data/backup --password='zzzzzzzzzzzzzz' --incremental-basedir=/data/backup/2013-11-21_22-50-22
    backup_cmd = "innobackupex --incremental %s --password='%s' --incremental-basedir=%s" % (backup_directory_path,password,os.path.join(backup_directory_path,base_backup_dir))
    debug_print(backup_cmd,verbosity)
    return_value = exeucte_command(backup_cmd,test_mode)
    if return_value != 0:
      throws("Backup did not execute successfully, executed %s, returned %d" % backup_cmd,return_value)
  ############################
  # 2. Full backup           #
  ############################
  elif backup_type == "full":
    # 2. full backups are performed in 2 commands, we get the directory after executing the first
    # 2.1 perform the backup
    backup_cmd = "innobackupex %s" % (backup_directory_path)
    debug_print(backup_cmd,verbosity)
    return_value = exeucte_command(backup_cmd,test_mode)
    if return_value != 0:
      throws("Backup did not execute successfully, executed %s, returned %d" % backup_cmd,return_value)

    # 2.2 apply the backup log to the last new directory
    full_backup_dir = directory_entry(backup_directory_path,-1)
    backup_cmd = "innobackupex --apply-log %s" % os.path.join(backup_directory_path,full_backup_dir)
    debug_print(backup_cmd,verbosity)
    return_value = exeucte_command(backup_cmd,test_mode)
    if return_value != 0:
      throws("Backup did not execute successfully, executed %s, returned %d" % backup_cmd,return_value)
  elif backup_type != None:
    throws("Unknown backup " % backup_type)

  # 3. get the new backup new_backup_dir since it will now be the last item in the directory, copy to s3
  # aws s3 cp 2013-11-23_15-38-07 s3://health-union-backups/2013-11-23_15-38-07 --recursive
  new_backup_dir = directory_entry(backup_directory_path,-1)
  new_backup_name = new_backup_dir
  # full backups get a special tag for ease of use
  if backup_type == "full":
    new_backup_name += "-full"
  s3_cp_cmd = "aws s3 cp %s s3://%s/%s --recursive" % (os.path.join(backup_directory_path,new_backup_dir),bucket,new_backup_name)

  debug_print(s3_cp_cmd,verbosity)
  return_value = exeucte_command(s3_cp_cmd,test_mode)

  if return_value != 0:
    throws("S3 copy did not execute successfully, executed %s, returned %d" % (s3_cp_cmd, return_value))

  # 4. remove the last backup directory, now the first enty in the list
  oldest_backup_dir = directory_entry(backup_directory_path,0)
  try:
    if remove_files:
      debug_print("Removing %s" % os.path.join(backup_directory_path,oldest_backup_dir),verbosity)
      shutil.rmtree(os.path.join(backup_directory_path,oldest_backup_dir))
  except:
    throws("Unable to remove oldest directory %s" % oldest_backup_dir)

if __name__ == "__main__":
  main()
