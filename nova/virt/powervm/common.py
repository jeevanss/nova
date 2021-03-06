# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 IBM
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import ftplib
import os

import paramiko

from nova import exception as nova_exception
from nova.openstack.common import log as logging
from nova.virt.powervm import exception

LOG = logging.getLogger(__name__)


class Connection(object):

    def __init__(self, host, username, password, port=22):
        self.host = host
        self.username = username
        self.password = password
        self.port = port


def ssh_connect(connection):
    """Method to connect to remote system using ssh protocol.

    :param connection: a Connection object.
    :returns: paramiko.SSHClient -- an active ssh connection.
    :raises: PowerVMConnectionFailed
    """
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(connection.host,
                    username=connection.username,
                    password=connection.password,
                    port=connection.port)
        return ssh
    except Exception:
        LOG.exception(_('Connection error connecting PowerVM manager'))
        raise exception.PowerVMConnectionFailed()


def ssh_command_as_root(ssh_connection, cmd, check_exit_code=True):
    """Method to execute remote command as root.

    :param connection: an active paramiko.SSHClient connection.
    :param command: string containing the command to run.
    :returns: Tuple -- a tuple of (stdout, stderr)
    :raises: nova.exception.ProcessExecutionError
    """
    LOG.debug(_('Running cmd (SSH-as-root): %s') % cmd)
    chan = ssh_connection._transport.open_session()
    # This command is required to be executed
    # in order to become root.
    chan.exec_command('ioscli oem_setup_env')
    bufsize = -1
    stdin = chan.makefile('wb', bufsize)
    stdout = chan.makefile('rb', bufsize)
    stderr = chan.makefile_stderr('rb', bufsize)
    # We run the command and then call 'exit' to exit from
    # super user environment.
    stdin.write('%s\n%s\n' % (cmd, 'exit'))
    stdin.flush()
    exit_status = chan.recv_exit_status()

    # Lets handle the error just like nova.utils.ssh_execute does.
    if exit_status != -1:
        LOG.debug(_('Result was %s') % exit_status)
        if check_exit_code and exit_status != 0:
            raise nova_exception.ProcessExecutionError(exit_code=exit_status,
                                                       stdout=stdout,
                                                       stderr=stderr,
                                                       cmd=' '.join(cmd))

    return (stdout, stderr)


def ftp_put_command(connection, local_path, remote_dir):
    """Method to transfer a file via ftp.

    :param connection: a Connection object.
    :param local_path: path to the local file
    :param remote_dir: path to remote destination
    :raises: PowerVMFileTransferFailed
    """
    try:
        ftp = ftplib.FTP(host=connection.host,
                         user=connection.username,
                         passwd=connection.password)
        ftp.cwd(remote_dir)
        name = os.path.split(local_path)[1]
        f = open(local_path, "rb")
        ftp.storbinary("STOR " + name, f)
        f.close()
        ftp.close()
    except Exception:
        LOG.error(_('File transfer to PowerVM manager failed'))
        raise exception.PowerVMFTPTransferFailed(ftp_cmd='PUT',
                source_path=local_path, dest_path=remote_dir)


def ftp_get_command(connection, remote_path, local_path):
    """Retrieve a file via FTP

    :param connection: a Connection object.
    :param remote_path: path to the remote file
    :param local_path: path to local destination
    :raises: PowerVMFileTransferFailed
    """
    try:
        ftp = ftplib.FTP(host=connection.host,
                         user=connection.username,
                         passwd=connection.password)
        ftp.cwd(os.path.dirname(remote_path))
        name = os.path.basename(remote_path)
        LOG.debug(_("ftp GET %(remote_path)s to: %(local_path)s") % locals())
        with open(local_path, 'w') as ftpfile:
            ftpcmd = 'RETR %s' % name
            ftp.retrbinary(ftpcmd, ftpfile.write)
        ftp.close()
    except Exception:
        LOG.error(_("File transfer from PowerVM manager failed"))
        raise exception.PowerVMFTPTransferFailed(ftp_cmd='GET',
                source_path=remote_path, dest_path=local_path)


def aix_path_join(path_one, path_two):
    """Ensures file path is built correctly for remote UNIX system

    :param path_one: string of the first file path
    :param path_two: string of the second file path
    :returns: a uniform path constructed from both strings
    """
    if path_one.endswith('/'):
        path_one = path_one.rstrip('/')

    if path_two.startswith('/'):
        path_two = path_two.lstrip('/')

    final_path = path_one + '/' + path_two
    return final_path
