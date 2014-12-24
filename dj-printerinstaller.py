#!/usr/bin/env python
'''Installer script for django WebApp printer-installer'''
import os
import sys
import site
import getpass
import webbrowser
import subprocess
import readline
import atexit
import glob

from socket import gethostname
from shutil import copyfile, move
from plistlib import writePlistToString
from tempfile import NamedTemporaryFile


global_settings = {
'PROJECT_NAME':'printerinstaller',
'PROJECT_DESCRIPTION':'Printer-Installer Server',

'PROJECT_REVERSE_DOMAIN':'com.github.eahrold',
'GIT-REPO':'https://github.com/eahrold/printerinstaller-server.git',
'GIT-BRANCH':'master',
'APACHE_SUBPATH':'printers',

## These setttings will be automatically altered in the settings file
'MODIFIED-SETTINGS':{ 
                    'LOGIN_URL':'django.contrib.auth.views.login',
                    'LOGOUT_URL':'django.contrib.auth.views.logout',
                    'LOGIN_REDIRECT_URL':'printers.views.manage',
                    },

# Custom Questions are tuples (key,message,type,default,require,values)
# See the Color class question method for more details
# The first argument is the value in the settings.py file that will be modified
'CUSTOM_QUESTIONS':[ 
        ('SERVE_FILES','Do you want to Serve PPD files?',bool,None,True,None),
        ('HOST_SPARKLE_UPDATES','Will you provide custom builds of PI Client?',bool,None,True,None),
        ],

'CUSTOM_APACE_CONFIG':{
        'APACHE_ALIAS':[
        # STATIC_URL is Aliased by default, MEDIA_URL can be added by simply listing that
                    'MEDIA_URL',
        # any others can be listed in tuple form either fully, or keys from settings.py
        # ('/path/','/path/to/virenv/project/files/path/')
        # ('MY_SETTING_URL','MY_SETTING_PATH')
        ],
# 'APACHE_PROTECTED_MEDIA_LOC':[]
# A path reletavive to MEDIA_URL to protect, 
# allow uploading files, but prevent downloading from...
        'APACHE_PROTECTED_MEDIA_LOC':['private'],
        }
}

class VirtualEnv(object):
    '''VirtualEnv'''
    class Error(Exception):
        '''Base class to raise when a VirtualEnv process fails'''
        pass

    class AvaliabilityError(Error):
        '''Exception to throw if virtualenv is unavaliable on the system'''
        pass

    class AccessError(Error):
        '''Exception to throw if the user cannot gain adequate priviledged'''
        pass

    def __init__(self, install_path):
        self.dir = install_path
        self.virtualenv = None

    @property 
    def pip(self):
        '''path to pip'''
        return os.path.join(self.dir, 'bin', 'pip')
    
    @property 
    def python(self):
        '''path to python'''
        return os.path.join(self.dir, 'bin', 'python') 
    
    @property
    def parent_dir(self):
        '''venv parent directory'''
        return os.path.abspath(os.path.join(self.dir, os.pardir))

    @property 
    def created(self):
        '''is the env created'''
        return True if os.path.isfile(self.python) else False
 
    def check_reqs(self, already_tried=False):
        '''check requirements'''
        try:
            import virtualenv
        except ImportError:
            try:
                if Colored.question('virtualenv is required to continue, install? ', bool):
                    subprocess.check_call(['easy_install', 'virtualenv'])
                    try:
                        import virtualenv
                    except:
                        raise VirtualEnv.AvaliabilityError( \
                            "Error: No virtualenv executable not found")
                else:
                    raise VirtualEnv.AvaliabilityError("virtualenv required, quitting...")
            except subprocess.CalledProcessError:
                raise VirtualEnv.AvaliabilityError("There was a problem installing virtualenv")

        self.virtualenv = virtualenv
        # check if there is write access to the parent directoy, 
        if not os.access(self.dir, os.W_OK):
            try:
                queston = 'Trying to install virtualenv in priviledged location, continue?'
                Colored.question(queston, type=bool)

                # make the directory, then set the ownership to the current user
                if not os.path.exists(self.dir):
                    subprocess.check_call(['sudo', 'mkdir', self.dir], stdout=subprocess.PIPE)
                
                subprocess.check_call(['sudo', 'chown', getpass.getuser(), \
                                        self.dir], stdout=subprocess.PIPE)

            except subprocess.CalledProcessError:

                raise VirtualEnv.AccessError(\
                    "Error: there was a problem elevating priviledges to the location")
                    
    def create(self):
        '''create the env'''
        if not self.created:
            try:
                self.check_reqs()
                self.virtualenv.create_environment(self.dir)
            except VirtualEnv.Error as _error:
                raise _error
            except subprocess.CalledProcessError as _error:
                raise VirtualEnv.Error(\
                    "There was a problem creating the Virtual Environment, exiting(%d)..." \
                        % _error.returncode)
        else:
            print "Environment already exists"

        self.activate()

    def activate(self):
        '''activate virtualenv'''
        if not self.created:
            self.create()
        print 'Activating virtual environment'
        activate_file = os.path.join(self.dir, "bin/activate_this.py")
        execfile(activate_file, dict(__file__=activate_file))
        
    def install_package(self, package):
        '''install package using pip'''
        subprocess.check_call([self.pip, 'install', package])

    def install_packages(self, requirements):
        '''install a collection of packages using requirement file'''
        try:
            pip_cmd = [self.pip, 'install']
            if type(requirements) is list:
                for i in requirements:
                    pip_cmd.append(i)
            else:
                if os.path.isfile(requirements):
                    pip_cmd.extend(['-r', requirements])
                else:
                    raise VirtualEnv.Error("Error: Requirements not properly specified!")
            subprocess.check_call(pip_cmd)
        except ValueError:
            print "A valid requirements file was not found"
        except subprocess.CalledProcessError:
            raise VirtualEnv.Error("There was a problem installing one or more of the requirements")
     

class DjangoInstallSettings(object):
    class Error(Exception):
        """Base class for exceptions in this module."""
        pass

    class RequiredSettingsError(Error):
        """Exception raised when required information is not supplied"""
        pass
 
    def __init__(self, **defaults): 
        ''' '''
        try:
            self.project_name = defaults['PROJECT_NAME']
            self.git_repo = defaults['GIT-REPO']
        except KeyError:
            raise DjangoInstallSettings.RequiredSettingsError("Requirements were not met")

        self.project_description = defaults.get('PROJECT_DESCRIPTION', self.project_name)

        self.project_reverse_domain = defaults.get('PROJECT_REVERSE_DOMAIN', 'django')

        self.project_dirname = defaults.get('PROJECT_DIRNAME', self.project_name)
        self.settings_dirname = defaults.get('SETTINGS_DIRNAME', self.project_name)
        
        self.custom_questions = defaults.get('CUSTOM_QUESTIONS')
        self.modified_settings = defaults.get('MODIFIED-SETTINGS', {})

        self.process_user = defaults.get('PROCESS_USER', self.project_name)
        self.process_group = defaults.get('PROCESS_GROUP', self.project_name)
        self.ssl_policy = 0

        self.isosxserver = True if os.path.exists('/Applications/Server.app') else False

        self.admin_name = 'admin'
        self.user_email = 'admin@example.com'
        self.user_pass = 'password'
        self.run_on_subpath = False
        self.apache_subpath = defaults.get('APACHE_SUBPATH', self.project_name)
        self.apache_aliases = []
        self.apache_protected_locations = []
        self.apache_custom_config = defaults.get('CUSTOM_APACE_CONFIG', {})
        self.server_host_name = gethostname()
        self.__requirements = defaults.get('REQUIREMENTS', \
                                     os.path.join('setup', 'requirements.txt'))

        self.webdata_dir = serverutil.serveradmin('web', 'dataLocation') \
                            if self.isosxserver else '/var/www/'

        self.git_branch = defaults.get('GIT-BRANCH', 'master')
        self.virtualenv_parent_dir = None


    @property 
    def virtualenv_dir(self):
        '''virtual environment directory'''
        return os.path.join(self.virtualenv_parent_dir, '%s_env' % self.project_dirname)

    @property 
    def project_dir(self):
        '''project directory'''
        return os.path.join(self.virtualenv_dir, self.project_dirname)

    @property 
    def settings_dir(self):
        '''settings directory'''
        return os.path.join(self.project_dir, self.settings_dirname)

    @property 
    def apache_sites_dir(self):
        '''apache sites directory'''
        distro = os.uname()[0]
        if self.isosxserver:            
            return os.path.join(self.webdata_dir, 'Sites')
        elif distro is 'Darwin':
            return os.path.join('/Library', 'WebServer', '')
        else:
            return self.webdata_dir

    @property
    def apache_config_dir(self):
        '''apache config file directory'''
        if self.isosxserver:
            return os.path.join('/', 'Library', 'Server', 'Web', 'Config', 'apache2')
        else:
            return os.path.join('/', 'etc', 'apache2', 'other')

    @property
    def apache_config_file(self):
        '''the config file local for the webapp'''
        return os.path.join(self.apache_config_dir, 'httpd_'+self.project_name+'.conf')

    @property 
    def osx_webapp_name(self):
        '''the os x webapp name'''
        return  '.'.join([self.project_reverse_domain, 'webapp', self.project_name,])
    
    @property 
    def osx_webapp_plist_file(self):
        return os.path.join(self.apache_config_dir, 'webapps', \
                            '.'.join([self.osx_webapp_name, 'plist']))
    
    @property
    def wsgi_file(self):
        '''location of wsgi file'''
        wsgi_file_name = '%s.wsgi' % self.project_name
        if self.isosxserver:
            return os.path.join(self.webdata_dir, 'WebApps', wsgi_file_name)
        else:
            return os.path.join(self.project_dir, wsgi_file_name)

    @property 
    def settings_file(self):
        '''location of the django settings.py'''
        return os.path.join(self.settings_dir, 'settings.py')

    @property
    def requirements(self):
        '''check the requirements type'''
        if type(self.__requirements) is list:
            return self.__requirements
        else:
            return os.path.join(self.project_dir, self.__requirements)
    
    @requirements.setter
    def requirements(self, value):
        '''set requirements'''
        self.__requirements = value

    @property
    def apache_custom_config(self):
        '''custom configuraton for apache'''
        pass 

    @apache_custom_config.setter
    def apache_custom_config(self, cc_dict=None):
        '''set apache custom config'''
        if type(cc_dict) is dict:
            self.apache_aliases = cc_dict.get('APACHE_ALIAS', [])
            self.apache_protected_locations = cc_dict.get('APACHE_PROTECTED_MEDIA_LOC', [])
    

    def prompt(self):
        '''prompt'''
        while True:
            Colored.echo("[1] www user" "(if you plan to run both non-secure(http) and secure(https))", 'purple')

            Colored.echo("[2] create a user %s and group %s" % \
                        (self.process_user, self.process_group), 'purple')

            resp = Colored.question('Please Choose', type=int, require=True, values=[1, 2])

            if resp == 2:
                if not serverutil.create_process_user_and_group(self.process_user, \
                                                                self.process_group):
                    if Colored.question(\
                        'There was a problem creating the user, run as www instead?', type=bool):

                        self.process_user = 'www'
                        self.process_group = 'www'
                        break
                    else:
                        raise
                else:
                    Colored.echo("You when running as an external user you can only run as one,\
                        \n[1] to run securly (https), or\n[2] to run on an insecure site(http) ", \
                        'purple')

                    self.ssl_policy = Colored.question('Choice: ', type=int, \
                                                       require=True, values=[1, 2]) is 1 and 1 or 3
                    break 
            else:
                self.process_user = 'www'
                self.process_group = 'www'
                break

        question = 'Where should we install the Virtual Environment '
        while True:
            self.virtualenv_parent_dir = Colored.question(question, \
                                    type=dir, default=self.apache_sites_dir, require=True)

            if Colored.question('Correct Path? %s ' \
              % self.virtualenv_dir, type=bool, color='purple'):
                break

        self.run_on_subpath = Colored.question(\
            'Would you like to run on the subpath "/%s"' % self.apache_subpath, bool)

        self.server_host_name = Colored.question('Enter the FQDN this will run on ', \
                                        type=str, default=self.server_host_name, require=True)

        user = getpass.getuser()
        email = "%s@%s" % (user, self.server_host_name)
        self.admin_name = Colored.question('Enter the username for the Django superuser ', \
                                            type=str, default=getpass.getuser())

        self.user_email = Colored.question('email address ', type=str, default=email)

        while True:
            self.user_pass = getpass.getpass("Password for the webapp's superuser: ")
            confirm = getpass.getpass('Confirm Password:')
            if not self.user_pass == confirm:
                print "Passwords did not match:"
            else:
                break
        
        for i in self.custom_questions:
            key, qst, typ, dft, req, val = i
            resp = Colored.question(qst, typ, dft, req, val)
            self.modified_settings[key] = resp


class DjangoApp(object):
    '''DjangoApp'''
    class Error(Exception):
        '''Exception to throw if a DjangoApp process fails'''
        pass

    class InstallError(Error):
        '''general error'''
        pass

    def __init__(self, virtualenv, install_settings):
        '''init'''
        if not isinstance(virtualenv, VirtualEnv):
            raise TypeError("Not a virtual environment")
        
        if not isinstance(install_settings, DjangoInstallSettings):
            raise TypeError("Not a Settings object")

        self.settings = install_settings
        self.virtualenv = virtualenv       
        self.name = self.settings.project_name
        self.app_diffsettings = {}
        
    @property
    def settings_py(self):
        '''settings file'''
        return self.settings.settings_file

    @property
    def manage_py(self):
        '''manage.py'''
        return os.path.join(self.settings.project_dir, 'manage.py')

    @property
    def media_root(self):
        '''media root'''
        return self.app_diffsettings.get('MEDIA_ROOT', None)

    @property
    def media_url(self):
        '''media url'''
        return self.app_diffsettings.get('MEDIA_URL', None)

    @property
    def static_root(self):
        '''static root'''
        return self.app_diffsettings.get('STATIC_ROOT', None)

    @property
    def static_url(self):
        '''static url'''
        return self.app_diffsettings.get('STATIC_URL')        

    def refresh_dj_settings(self):
        '''refresh settings'''
        compiled_settings = self.settings_py+'c'
        if os.path.isfile(compiled_settings):
            try:
                if os.access(compiled_settings, os.W_OK) and \
                   os.access(os.path.dirname(compiled_settings), os.W_OK):
                    os.remove(compiled_settings) 
                else:
                    rm_cmd = ['sudo', 'rm', self.settings_py +'c']
                    subprocess.check_call(rm_cmd)
            except (OSError, subprocess.CalledProcessError):
                print "There was a problem purging the compiled settings file"

        try:
            _settings = subprocess.check_output([self.virtualenv.python, \
                                                 self.manage_py, 'diffsettings'])

        except subprocess.CalledProcessError:
            pass
        else:
            _settings = _settings.split('\n')
            for _setting in _settings:
                try:
                    s_key = _setting.split('=')[0].strip(' ')
                    s_value = _setting.split('=')[1].strip('\'"# ')
                    self.app_diffsettings[s_key] = s_value
                except IndexError:
                    pass

    def get_dj_setting(self, key):
        '''get django settings'''
        # django holds on to settings so remove the compiled settings file
        if os.path.exists(self.settings_py +'c'):
            os.remove(self.settings_py +'c') 

        _settings = subprocess.check_output([self.virtualenv.python, \
                                             self.manage_py, 'diffsettings'])
        _settings = _settings.split('\n')
        for _setting in _settings:
            if key in _setting:
                return _setting.split('=')[1].strip('\'"# ')


    def download_git_repo(self):
        '''download repo'''
        try:
            git = which('git')
            dest = self.settings.project_dir
            repo = self.settings.git_repo
            branch = self.settings.git_branch

            if os.path.exists(dest):
                git_dest = dest
            # probably should attempt a git pull
                # check to see if this is really a git repo first
                if not os.path.isdir(os.path.join(dest, '.git')):
                    raise DjangoApp.Error('Specified location exists and is not a git repo')
                else:
                    if Colored.question('Repo alredy exists, would you like to pull new changes?', bool):
                        command = ['git', 'pull', '--no-edit']
                    else:
                        return  
            else:
                git_dest = '/'
            # git the repo
                command = [git, 'clone', '-b', branch, repo, dest] 
            subprocess.check_call(command, cwd=git_dest)
        except Exception:
            raise DjangoApp.Error('Specified location exists and is not a git repo')


    def install(self):
        '''Install webapp'''
        self.virtualenv.create()
        self.download_git_repo()

        try:
            self.virtualenv.install_packages(self.settings.requirements)
            self.configure_django_settings()
        except:
            raise
       
        # now that everything is installed and configured
        # we should be able to import our django modules

        sys.path.extend([self.settings.project_dir, self.settings.settings_dir])
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', '%s.settings' % self.name)

        try:
            from django.core.management import call_command
            from django.contrib.sites.models import Site
            from django.contrib.auth.models import User
            
            import django
            django.setup()
            
            print "config done"

            call_command('syncdb', interactive=False, load_initial_data=False, verbosity=0)
            call_command('migrate', verbosity=0)
            call_command('collectstatic', interactive=False, verbosity=0)
        except ImportError as e:
            print 'couldn not import %s' % e
        except Exception as e:
            print "Erro %s" % e
            raise

        print "config done"

        # set up the site based on supplied hostname
        try:
            Site.objects.create(domain=self.settings.server_host_name, \
                                name=self.settings.server_host_name)
        except Exception:
            print "A non-critical error occured while creating the site,\
                you may need to do this manually using the Admin portal"

        # create a superuser
        try:
            User.objects.create_superuser(self.settings.admin_name, \
                                          self.settings.user_email, \
                                          self.settings.user_pass)
        except Exception:
            print "A super user has already been created, skipping"
        

        self.configure_apache_components()
        self.set_permissions()

    def configure_django_settings(self):
        '''handle the locating and manipulating of the settings.py file'''
        from django.utils.crypto import get_random_string
        import time

        settings_template = None
        search_for = os.path.join(self.settings.settings_dir, '*settings*.py')

        for name in glob.glob(search_for):
            if not name == self.settings.settings_file:
                settings_template = name
                break
        
        if not settings_template: 
            raise DjangoApp.Error("could not find settings file, cannot continue...")

        DjangoConfigFile.copy(settings_template, self.settings.settings_file)
        
        # Sleep for a second to be sure the file gets copied, just to be safe.
        time.sleep(1)

        # Generate a new secret key
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        self.settings.modified_settings['SECRET_KEY'] = get_random_string(50, chars)
        
        self.settings.modified_settings['ALLOWED_HOSTS'] = ['%s' % self.settings.server_host_name]

        if self.settings.run_on_subpath:
            self.refresh_dj_settings()

            sup_path = self.settings.apache_subpath
            media_url = self.media_url[1:] if self.media_url.startswith('/') else self.media_url
            self.settings.modified_settings['MEDIA_URL'] = \
                                os.path.join('/', sup_path, media_url, '')

            # if not self.settings.modified_settings.get('STATIC_URL',None):
            static_url = self.static_url[1:] if self.static_url.startswith('/') \
                                             else self.static_url
            self.settings.modified_settings['STATIC_URL'] = \
                                os.path.join('/', sup_path, static_url, '')

        DjangoConfigFile(self.settings.settings_file).edit_settings_py(self.settings.modified_settings)

        # now that the modifications have been done, update the internal values
        self.refresh_dj_settings()


    def configure_apache_components(self):
        '''config apache'''
        for index, item  in enumerate(self.settings.apache_aliases):
            if type(item) is tuple:
                alias, path = item
                # if both look like paths add them 
                if '/' in alias and '/' in path:
                    self.settings.apache_aliases[index] = item
                else:
                    alias = self.get_dj_setting(alias) 
                    path = self.get_dj_setting(path)
                    if alias and path:
                        self.settings.apache_aliases[index] = (alias, path)
            elif item in ['MEDIA_URL', 'MEDIA_ROOT']:
                self.settings.apache_aliases[index] = (self.media_url, self.media_root)
        
        self.settings.apache_aliases.append((self.static_url, self.static_root))
        
        if self.settings.apache_protected_locations:
            media_url = self.media_url
            for i, loc in enumerate(self.settings.apache_protected_locations):
                self.settings.apache_protected_locations[i] = (os.path.join(media_url, loc))


        DjangoConfigFile(self.settings.apache_config_file).write_apache_conf(self.settings)
        DjangoConfigFile(self.settings.wsgi_file).write_wsgi(self.settings)
        if self.settings.isosxserver:
            DjangoConfigFile(self.settings.osx_webapp_plist_file).write_webapp_plist(self.settings)

        return True

    def set_permissions(self, **kwargs):
        '''set permission'''
        user = kwargs.get('user', self.settings.process_user)
        group = kwargs.get('group', self.settings.process_group)
        env_path = kwargs.get('path', self.virtualenv.dir)
        Colored.echo("Configuring permission on web application files", 'purple')

        mod_perms = [(self.settings.settings_file, 700), \
                     (self.media_root, 755), \
                     (os.path.join(self.settings.settings_dir, \
                        self.settings.project_name+'.db'), 700)]

        chown_cmd = ['sudo'] if os.geteuid() != 0 else []
        chmod_cmd = ['sudo', 'chmod'] if os.geteuid() != 0 else []

        chown_cmd.extend(['chown', '-R', '%s:%s'%(user, group), env_path])
               
        try:
            subprocess.check_call(chown_cmd)
            for i in self.settings.apache_protected_locations:
                mod_perms.append((os.path.join(self.media_root, i), 700))

            for i in mod_perms:
                path, perm = i
                if os.path.exists(path):
                    subprocess.check_call(chmod_cmd+[str(perm), path])
        except subprocess.CalledProcessError as _error:
            print _error

class DjangoConfigFile(object):
    '''Django configuration file'''
    class Error(Exception):
        '''Exception to throw if a DjangoConfigFile write process fails'''
        pass

    class WriteError(Error):
        '''Exception to throw if a DjangoConfigFile write process fails'''
        pass
    
    class PriviledgedProcessError(Error):
        '''Exception to throw if a DjangoConfigFile write process fails'''
        pass

    class ReadError(Error):
        '''Exception to throw if a DjangoConfigFile read process fails'''
        pass

    class TypeError(Error):
        '''Exception to throw if a DjangoConfigFile read process fails'''
        pass

    class CopyError(Error):
        '''Exception to throw if a DjangoConfigFile copy process fails'''
        pass

    def __init__(self, filename):
        '''Write and Configure files'''
        self.file = filename
        self.__file_array = []

    @classmethod
    def copy(self, from_file, to_file):
        try:
            if self.priviledged_location:
                subprocess.call(['sudo', 'cp', '-f', '-p', from_file, to_file])
            else:
                copyfile(from_file, to_file)
        except subprocess.CalledProcessError:
            raise DjangoConfigFile.PriviledgedProcessError( \
                    'Error copying file to priviledged location')
        except OSError:
            raise DjangoConfigFile.CopyError('Error copying file')

    @property
    def priviledged_location(self):
        ''' checks if the the file is priviledged from the user
            returns True if it is priviledged, indicating the user 
            CANNOT write to the location in the current context,
            and False if the user CAN write to the location
        '''
        # this is a directory, and we're looking for files!
        if os.path.isdir(self.file):
            raise DjangoConfigFile.TypeError( \
                'The item specified is a directory, but should be a file')

        #if file exists return True
        elif os.path.isfile(self.file):
            return False if os.access(self.file, os.W_OK) else True
        #else check if there is write priv to directory
        else:
            return False if os.access(os.path.dirname(self.file), os.W_OK) else True

    def write(self, joint=""):
        '''write to file'''

        tmp_file_string = joint.join(self.__file_array)
        try:
            if self.priviledged_location == True:
                file_name = os.path.basename(self.file)
                if Colored.question("Write file '%s' to priviledged path? " \
                                    % file_name, bool, color='red'):
                    print "\n"
                    try:
                        temp_file = NamedTemporaryFile(mode='w+t')
                        file_name = temp_file.name

                        temp_file.write(tmp_file_string)
                        temp_file.flush()

                        subprocess.check_call(['sudo', 'cp', '-f', file_name, self.file])
                        temp_file.close()

                    except Exception, e:
                        print e

                   
                    

            elif self.priviledged_location == False:
                with open(self.file, 'w') as _file:
                    _file.write(tmp_file_string)
        except subprocess.CalledProcessError:
            raise DjangoConfigFile.PriviledgedProcessError('Error writing to priviledged location')
        
        except DjangoConfigFile.TypeError as _error:
            raise DjangoConfigFile.WriteError(_error)
        
        except Exception:
            raise DjangoConfigFile.WriteError('Error writing the file')

    def setting_replace(self, key, replacement):
        '''replace settings in the actual settings.py file
        the __file_array is a store for line of the file'''
        for index, name in enumerate(self.__file_array):
            dont_quote = ['os', 'sys', "'", '"']
            # make sure things that should be quoted, are
            if not type(replacement) in [bool, list, dict, tuple]:
                if not replacement[0] in dont_quote:
                    replacement = "'%s'" % replacement

            # get this here to preserve indentation
            key_match = name.split('=')[0]
            if key == key_match.strip():
                substr = '%s = %s\n' % (key_match, replacement)
                self.__file_array[index] = substr
    
    
    def edit_settings_py(self, settings_dict=dict):
        '''write the settings.py file with the changed 
        values stored in the __file_array'''
        # open the file and get it into memory
        with open(self.file, 'r') as _file:
            for line in _file:
                self.__file_array.append(line)

        # modify all the settings you wish to here
        for key, value in settings_dict.iteritems():
            self.setting_replace(key, value)

        # finish up and write out to the file
        self.write("")

    def write_wsgi(self, settings):
        '''write the wsgi file .The settings passed in is a 
        DjangoInstallSettings object'''

        self.__file_array = [ \
            "", \
            "''' WSGI file created using autoinstall script '''", \
            "import os, sys", \
            "import site", \
            "", \
            "VIR_ENV_DIR = '%s'" % settings.virtualenv_dir, \
            "", \
            "# Use site to load the site-packages directory of our virtualenv", \
            "site.addsitedir(os.path.join(VIR_ENV_DIR, 'lib/python2.7/site-packages'))", \
            "", \
            "# Make sure we have the virtualenv and the Django app itself added to our path", \
            "sys.path.append(VIR_ENV_DIR)", \
            "sys.path.append(os.path.join(VIR_ENV_DIR, '%s'))" % settings.project_dirname, \
            "", \
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', '%s.settings')" % settings.settings_dirname, \
            "",\
            "from django.core.handlers.wsgi import WSGIHandler",\
            "application = WSGIHandler()",\
            "",\
            "from django.core.wsgi import get_wsgi_application",\
            "module=get_wsgi_application()",\
            "",\
            ]

        self.write("\n")

    def write_site_fixture(self, settings):
        '''TODO: Write site fixture dynamically 
        from user initial user input'''
        self.__file_array = []
        self.write("\n")

    def write_apache_conf(self, settings):
        '''write apache config file for webapp'''
        # The settings is a DjangoInstallSettings object passed in

        self.__file_array = ['WSGIScriptAlias /%s %s' % \
                            (settings.apache_subpath if settings.run_on_subpath else '',
                             settings.wsgi_file)]

        for item in settings.apache_aliases:
            alias, path = item
            self.__file_array.append('Alias %s %s' % (alias, path))

        if not settings.process_user is 'www':
            self.__file_array.extend([
                'WSGIDaemonProcess %s user=%s group=%s' % (settings.project_name,settings.process_user, settings.process_group),
                '<Location /%s>' % settings.apache_subpath if settings.run_on_subpath else '',
                '   WSGIProcessGroup %s' % settings.project_name,
                '    WSGIApplicationGroup %{GLOBAL}',
                '    Order deny,allow',
                '    Allow from all',
                '</Location>',
                '',
                ])

        for location in settings.apache_protected_locations:
            self.__file_array.extend([
                '<Location %s>' % location,
                '    Order Allow,Deny',
                '    Deny from  all',
                '</Location>',
                ])
        self.write("\n")

    def write_webapp_plist(self, settings):
        '''write webapp plist to file'''

        plist = {'displayName':settings.project_description, \
                 'includeFiles':[settings.apache_config_file], \
                 'installationIndicatorFilePath':settings.wsgi_file, \
                 'name':settings.osx_webapp_name, \
                 'requiredModuleNames':['wsgi_module',], \
                 'sslPolicy':settings.ssl_policy, \
                }

        plist_string = writePlistToString(plist)
        self.__file_array.append(plist_string)
        self.write("")

class DSRecord(object):
    ''' work with Directory Service, add user and groups
        create an authorized object do

        credentials = DSRecord.credentials('username','password')
        ds = DSRecord(credentials)
        user = DSRecord.user('username','uid','password'...)
        ds.add(user)
    '''
    class Error(Exception):
        '''Exception to throw if DSRecord process fails'''
        pass

    def __init__(self, credentials=None, node='.'):
        self.credentials = credentials
        self.node = node
        self.id_search_start = 1025
        self.id_search_max = 2000
        self.__dscl_base = []
                
    class credentials:
        '''Credentials Object'''
        def __init__(self, admin=None, password=None):
            self.admin = admin
            self.password = password
    
    class user:
        '''User Object'''
        def __init__(self, name, uid=None, password='*', gid=20, shell='/bin/bash', home='/dev/null'):
            self.name = name
            self.uid = uid
            self.realname = name 
            self.password = password
            self.primary_gid = gid
            self.shell = shell
            self.home = home
               
    class group:
        '''Group object'''
        def __init__(self, name, gid=None):
            self.name = name
            self.gid = gid
    
    def ldap_user_setup(self, host):
        '''constructs not for LDAPv3 domain'''
        self.node = os.path.join('/LDAPv3/', host)

    def system_user_setup(self):
        '''Constructs node for local domain'''
        self.id_search_start = 400
        self.id_search_max = 500
        self.node = '.'
        
    def dscl(self,args=[]):
        '''wrapper for the directory service command line'''
        __dscl = ['dscl']

        if self.credentials and self.credentials.admin and self.credentials.password:
            __dscl.extend(['-u', self.credentials.admin, '-P', self.credentials.password])

        elif 'create' in self.__dscl_base or 'create' in args:
            __dscl.insert(0, 'sudo')
        

        __dscl.extend([self.node]) 
        if self.__dscl_base and not args == self.__dscl_base:
            __dscl.extend(self.__dscl_base)
        
        __dscl.extend(args)

        try:
            output =  subprocess.check_output(__dscl)
            return output
        except subprocess.CalledProcessError as _error:
            print "Problem executing the DSCL command"
            raise DSRecord.Error(_error)
    
    def get_valid_id(self, path, key):
        '''gets the next avaliable ID number
        for a given type of dscl object'''

        list_cmd = ['list', '/%s' % path, key]

        vid = self.id_search_start
        vids = self.dscl(list_cmd)

        arr = []
        for item in vids:
            item_arr = item.split()
            if item_arr and len(item_arr) > 1:
                arr.append(item_arr[1])

        while vid < self.id_search_max:
            if str(vid) in arr:
                vid += 1
            else:
                return str(vid)

        # if we make it here something is wrong
        raise DSRecord.Error('could not a valid unique id in range')
    
    def add(self, record, update=False):
        '''Add a dscl record object'''
        try:
            if isinstance(record, DSRecord.user): 
                import pwd
                self.__dscl_base = ['create', '/Users/%s' % record.name]
                try:
                    err_msg = 'There was a problem creating the %s user record' % record.name
                    uid = pwd.getpwnam(record.name).pw_uid
                    record.uid = record.uid or uid
                    print 'User "%s" already exists' % record.name
                except Exception:
                    print 'Creating user "%s"' % record.name
                    record.uid = record.uid or self.get_valid_id('Users', 'UniqueID')
                    self.dscl()
                    update = True
                
                if update:
                    print 'Updating user record'
                    err_msg = 'There was a problem updating the "%s" user record' % record.name
                    self.dscl(['RealName', record.name])
                    self.dscl(['UniqueID', str(record.uid)])
                    self.dscl(['passwd', record.password])
                    self.dscl(['UserShell', record.shell]) 
                    self.dscl(['NFSHomeDirectory', record.home])
                    self.dscl(['PrimaryGroupID', str(record.primary_gid)])
                
            elif isinstance(record, DSRecord.group):
                import grp
                err_msg = 'There was a problem creating the "%s" group record' % record.name
                try:
                    gid = grp.getgrnam(record.name).gr_gid
                    record.gid = record.gid or gid
                    print 'group "%s" already exists' % record.name
                except Exception:
                    update = True
                    
                if update:
                    err_msg = 'There was a problem updating the "%s" group record' % record.name

                    if not record.gid:
                        record.gid = self.get_valid_id('Groups', 'PrimaryGroupID')

                    grp_cmd = ['sudo','dseditgroup', '-o', 'create', '-r', \
                                record.name, '-i', str(record.gid), '-n', '.']

                    admin = None
                    password = None
                    if self.credentials:
                        admin = self.credentials.admin
                        password = self.credentials.password
                       
                    if admin and password:
                        grp_cmd.extend(['-u', admin, '-P', password])
                    
                    grp_cmd.append(record.name)
                    subprocess.check_output(grp_cmd)

            
            print ' Successfully added record' if update else '  skipping...'

        except DSRecord.Error as error:
            raise error
        except:
            raise DSRecord.Error(err_msg)
        finally:
            self.__dscl_base = []

class PostgresAdmin:
    '''Not implemented yet'''
    class Error(Exception):
        pass

    def __init__(self, **kwargs):
        self.user = kwargs.get('admin', '_postgres')
        self.password = kwargs.get('password')

    def exec_command(self, command_args):
        pass
    
    def createuser(self):
        '''creat new user'''
        createuser = ['sudo', 'createuser','--username=_postgres', self.dbowner]
        self.exec_command(createuser)

    def createdb(self):
        '''create new database'''
        createdb = ['sudo', 'createdb', '--username=_postgres', '-O', self.dbname]
        self.exec_command(createdb)


    def setpasswd(self):
        '''set password'''
        setpsswd = ['sudo', 'psql', '--username=_postgres', '-d', 'postgres', '-c', "alter user %s with password '%s';" %(dbowner, dbowner_pass)]
        self.exec_command(setpsswd)


    def create_db_and_owner(self, dbname, dbowner, dbowner_pass):
        '''create a database and password'''

        __psql_base = ['sudo', 'psql', '--username=_postgres', '-d', 'postgres', '-c']
        # self.createuser()
        # self createdb()
        # self.setpsswd()
        # psql -U _postgres template1 -c "CREATE USER my_user_name WITH password 'opensaysme';"
        # CREATE DATABASE mydb WITH OWNER my_user_name;

class serverutil:
    class Error(Exception):
        '''Exception to throw if serverutil process fails'''
        pass

    def __init__(self):
        pass

    @classmethod
    def webappctl(cls, webapp, command='restart', vhost=None):
        '''Wrapper for the webappctl command line utility'''
        wac = '/Applications/Server.app/Contents/ServerRoot/usr/sbin/webappctl'
        try:
            webapp_cmd = ['sudo', wac, command, webapp,]
            if vhost:
                webapp_cmd.extend(['-', vhost])

            subprocess.check_call(webapp_cmd)    
        except subprocess.CalledProcessError:
            raise serverutil.Error('Could not start webapp')

    @classmethod
    def serveradmin(cls, module, value):
        '''Wrapper for the serveradmin comand line utility'''
        ssad = '/Applications/Server.app/Contents/ServerRoot/usr/sbin/serveradmin'
        default_path = '/Library/Server/Web/Data'
        try:
            ssad_command = ['sudo', ssad, 'settings', ':'.join([module, value])]
            results = subprocess.check_output(ssad_command)    
            string = results.split('=')[1].strip().strip('\"')
            if not string in ('_empty_dictionary',):
                return string
        except Exception:
            pass
        return default_path

    @classmethod
    def create_process_user_and_group(cls, process_user, process_group):
        '''Try to create the process user for the django webapp'''
        try:
            user = DSRecord.user(process_user)
            group = DSRecord.group(process_group)
            record = DSRecord()
            record.system_user_setup()
            record.add(group)
            print "added group"
            user.primary_gid = group.gid
            record.add(user)
            print "added user"
            return True
        except Exception as _error:
            raise _error

class Colored:
    '''Simple class to print colored text to terminal'''
    def __init__(self):
        pass

    @classmethod
    def ansii_color_str(cls, message, color=None):
        '''create colored string from keywords'''
        if color in ('red', 'alert'):
            c_val = '31'
        elif color in ('green', 'attention'):
            c_val = '32'
        elif color in ('yellow', 'warn'):
            c_val = '33'
        elif color in ('blue', 'question'):
            c_val = '34'
        elif color in ('purple', 'info'):
            c_val = '35'
        elif color in ('cyan', 'notice'):
            c_val = '36'
        elif color in ('bold', 'prompt'):
            c_val = '37'
        else:
            c_val = '0'

        attr = ['1']
        attr.append(c_val)
        color_string = '\x1b[%sm%s\x1b[m' % (';'.join(attr), message)
        return color_string

    @classmethod
    def read(cls, message, color=None, type=str):
        '''read user input'''
        string = raw_input(Colored.ansii_color_str(message, color))
        if type is bool:
            if string in ('Y', 'y', 'Yes', 'yes', 'YES'):
                return True
            elif string in ('N', 'n', 'No', 'no', 'NO'):
                return False
        else:
            return string
    
    @classmethod
    def echo(cls, message, color=None):
        '''echo'''
        print cls.ansii_color_str(message, color)

    @classmethod
    def question(cls, message, type=str, default={}, require=True, values=[], color='question'):
        while True:
            prompt = message
            if type == bool:
                prompt = message + '[(Y)es/(N)o]'
            elif default:
                prompt = message + '[%s]'% default

            prompt = prompt + ': '
            ret = cls.read(prompt, color=color, type=type)
            if type == bool:
                if ret in (True, False):
                    break
                else:
                    cls.echo("Please answer Yes or No", 'alert')

            elif type == file:
                if not ret and default:
                    ret = default
                if require and not os.path.exists(ret):
                    cls.echo("There's No file at that path", 'alert')
                else:
                    break

            elif type == dir:
                if not ret and default:
                    ret = default
                if require and not os.path.isdir(ret):
                    cls.echo("There's No directory at that path", 'alert')
                else:
                    break

            elif type == int:
                try:
                    ret = int(ret)
                    if values and not ret in values:
                        raise ValueError()
                    break
                except ValueError:
                    cls.echo("Please choose form these values %s" % values, 'alert')
            else:  # type is string
                if default and not ret:
                    ret = default
                if require and not ret:
                    cls.echo("There was an empty response", 'alert')
                else:
                    break
        return ret

def which(exe):
    '''find executable from user's PATH environment'''
    def is_executable(exe_path):
        '''Is exe_path executable?'''
        return os.path.exists(exe_path) and os.access(exe_path, os.X_OK)

    for path_env in os.getenv("PATH").split(os.pathsep):
        exe_path = os.path.join(path_env, exe)
        if is_executable(exe_path):
            # take the first found executable in PATH
            return exe_path
            
    return None



def main(*argv, **kwargs):
    def complete(text, state):
        '''call when complete'''
        return (glob.glob(text+'*')+[None])[state]

    def find_owner(filename):
        '''determine the file owner'''
        from pwd import getpwuid
        return getpwuid(os.stat(filename).st_uid).pw_name

    def terminal_size():
        '''Get the current terminal width and height'''
        import fcntl, termios, struct

        # fd = os.open(os.ctermid(), os.O_RDONLY)
        current_resolution = struct.unpack('hh', \
            fcntl.ioctl(0, termios.TIOCGWINSZ, '1234'))
        
        return int(current_resolution[1]), int(current_resolution[0])

    def setup_tab_complete():
        '''enable path tab completion'''
        if 'libedit' in readline.__doc__:
            readline.parse_and_bind("bind -e")
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
        readline.set_completer(complete)
    
    def print_banner():
        '''print the initial banner message'''
        subprocess.call(['resize', '-s', '40', '100'])
        clear = lambda: os.system('clear')
        clear()

        colored = Colored
        info_str = 'Django WebApp %s installer' % install_settings.project_description
        
        width, height = terminal_size()
        full_line = width if len(info_str) % 2 == 0 else width - 1
        pounds_count = full_line / 6
        space_count = int((full_line - len(info_str))/2) - pounds_count
        colored.echo("#"*full_line, 'red')
        colored.echo("".join(["#"*pounds_count, " "* space_count, info_str, \
                        " "*space_count, "#"*pounds_count]), 'red')
        colored.echo("#"*full_line, 'red')

    try:
        original_project_owner = None
        app = None
        error = None

        setup_tab_complete()
        install_settings = DjangoInstallSettings(**kwargs)
        print_banner()

        install_settings.prompt()

        # once we've got our settings back, check
        # to see who the owner is, stash that, and
        # set the current user as the owner of the file 
        env_path = install_settings.virtualenv_dir
        if os.path.exists(env_path):
            original_project_owner = find_owner(env_path)
            current_user = getpass.getuser()
            try:
                print "Temporairly setting owner to %s" % current_user
                subprocess.check_call(['sudo', 'chown', '-R', current_user, env_path])
            except subprocess.CalledProcessError as _error:
                print "ERROR: Could not set owner"

        venv = VirtualEnv(env_path)

        app = DjangoApp(venv, install_settings)
        app.install()


        if Colored.question('Do you want to start the webapp on the default server? ', type=bool):
            serverutil.webappctl(install_settings.osx_webapp_name)

    except Exception as _error:
        error = True
        raise _error
    finally:
        if original_project_owner and error and app:
            print "ERROR OCCURED DURING RE-INSATLL: \
                   resetting priviledges to original owner %s" % original_project_owner

            subprocess.call(['sudo', 'chown', '-R', original_project_owner, env_path])


if __name__ == "__main__": 
    kwargs = global_settings
    try:
        main(*sys.argv, **kwargs)
    except KeyboardInterrupt:
        print "\nCanceling the Auto install script."
        