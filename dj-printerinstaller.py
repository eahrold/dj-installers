#!/usr/bin/env python

import os
import sys
import subprocess
import site
import atexit

from shutil import copyfile, move
from tempfile import NamedTemporaryFile
from plistlib import writePlistToString
from socket import gethostname

__defined_settings = {
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
# See the DjangoInstallSettings class question method for more details
# these are only related to the settings file
'CUSTOM_QUESTIONS':[ 
        ('SERVE_FILES','Do you want to Serve PPD files?',bool,None,True,None),
        ('HOST_SPARKLE_UPDATES','Will you provide custom builds of PI Client?',bool,None,True,None),
        ],

'CUSTOM_APACE_CONFIG':{
# only STATIC_URL is aliased by default, include any others here
        'APACHE_ALIAS':['MEDIA_URL',
        ## you could also add a tuple like ('/path/','/path/to/virenv/project/files/path/')
        ],
        #
# reletavive to MEDIA_URL to protect, allow uploading files here, but prevent downloading from...
        'APACHE_PROTECTED_MEDIA_LOC':['private'],
        }
}

class VirtualEnv(Exception):
        '''Exception to throw if a VirtualEnv process fails'''
        pass

class VirtualEnv(object):
    virtualenv_exe = None

    def __init__(self,path,name):
        self.name = name + '_env'
        self.dir = path
        self.path = os.path.join(path,self.name)
        
    @property 
    def pip(self):
        return os.path.join(self.path,'bin','pip')
    
    @property 
    def python(self):
        return os.path.join(self.path,'bin','python') 
    
    @property 
    def created(self):
        return True if os.path.isfile(self.python) else False
        
    def check_reqs(self):
        if not VirtualEnv.virtualenv_exe:
            VirtualEnv.virtualenv_exe = subprocess.check_output(['which','virtualenv'])
            if not VirtualEnv.virtualenv_exe:
                try:
                    print "trying to install virtualenv"
                    subprocess.check_call(['easy_install', 'virtualenv'])
                    self.check_requs()
                except subprocess.CalledProcessError as e:
                    raise VirtualEnvError("Error: No virtualenv executable not found")

        if not os.access(self.dir,os.W_OK):
            import getpass
            try:
                Colored.question('Trying to install virtualenv in priviledged location, continue? ',type=bool,)
                subprocess.check_call(['sudo','mkdir',self.path],stdout=subprocess.PIPE)
                subprocess.check_call(['sudo','chown',getpass.getuser(),self.path],stdout=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                raise VirtualEnvError("Error: there was a problem elevating priviledges to the location")
                    
    def create(self):
        if not self.created:
            self.check_reqs()
            try:
                subprocess.check_call(['virtualenv',self.path],stdout=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                raise VirtualEnvError("There was a problem creating the Virtual Environment, exiting(%d)..." % e.returncode)
        else:
            print "Environment already exists"
        self.activate()

    def activate(self):
        if not self.created:
            self.create()
        print 'Activating virtual environment'
        activate_file = os.path.join(self.path,"bin/activate_this.py")
        execfile(activate_file, dict(__file__=activate_file))
        
    def install_package(self,package):
        subprocess.check_call([self.pip, 'install', package])

    def install_packages(self,requirements):
        try:
            pip_cmd = [self.pip,'install']
            if type(requirements) is list:
                for i in requirements:
                    pip_cmd.append(i)
            else:
                if os.path.isfile(requirements):
                    pip_cmd.extend(['-r',requirements])
                else:
                    raise VirtualEnvError("Error: Requirements not properly specified!")
            subprocess.check_call(pip_cmd)
        except ValueError:
            print "A valid requirements file was not found"
        except subprocess.CalledProcessError:
            raise VirtualEnvError("There was a problem installing %s")
     

class DjangoInstallSettings(object):
    _isosxserver = True if os.path.exists('/Applications/Server.app') else False

    def __init__(self,project_name,defaults={}): 
        self.project_name = defaults.get('PROJECT_NAME',project_name)
        self.project_description = defaults.get('PROJECT_DESCRIPTION',project_name)

        self.project_reverse_domain = defaults.get('PROJECT_REVERSE_DOMAIN','django')

        self.project_dirname = defaults.get('PROJECT_DIRNAME',project_name)
        self.settings_dirname = defaults.get('SETTINGS_DIRNAME',project_name)
        
        self.custom_questions = defaults.get('CUSTOM_QUESTIONS',None)
        self.modified_settings = defaults.get('MODIFIED-SETTINGS',{})

        self.process_user = defaults.get('PROCESS_USER',project_name)
        self.process_group = defaults.get('PROCESS_GROUP',project_name)
        self.sslPolicy = 0

        self.admin_name = 'admin'
        self.user_email = 'admin@example.com'
        self.user_pass  = 'password'

        self.run_on_subpath = False
        self.apache_subpath = defaults.get('APACHE_SUBPATH',project_name)
        self.apache_aliases = []
        self.apache_protected_locations = []
        self.apache_custom_config = defaults.get('CUSTOM_APACE_CONFIG',{})
        self.server_host_name = gethostname()
        self.__requirements = defaults.get('REQUIREMENTS',os.path.join('setup','requirements.txt'))

        self.git_repo = defaults.get('GIT-REPO',None)
        self.git_branch = defaults.get('GIT-BRANCH','master')
        if not self.git_repo:
            raise ValueError

        self.webdata_dir = Util.serveradmin('web','dataLocation') if self._isosxserver else '/usr/local/www'


    @property 
    def virtualenv_dir(self):
        return os.path.join(self.virtualenv_path,'%s_env' % self.project_dirname)

    @property 
    def project_dir(self):
        return os.path.join(self.virtualenv_dir,self.project_dirname)

    @property 
    def settings_dir(self):
        return os.path.join(self.project_dir,self.settings_dirname)

    @property 
    def apache_sites_dir(self):
        distro = os.uname()[0]
        if self._isosxserver:            
            return os.path.join(self.webdata_dir,'Sites')
        elif os.uname()[0] is 'Darwin':
            return os.path.join('/Library','WebServer','')
        else:
            return os.path.join('/var','www')

    @property
    def apache_config_dir(self):
        if self._isosxserver:
            return os.path.join('/','Library','Server','Web','Config','apache2')
        else:
            return os.path.join('/','etc','apache2','other')

    @property
    def apache_config_file(self):
        return os.path.join(self.apache_config_dir,'httpd_'+self.project_name+'.conf')

    @property 
    def osx_webapp_name(self):
        return  '.'.join([self.project_reverse_domain,'webapp', self.project_name,])
    
    @property 
    def osx_webapp_plist_file(self):
        return os.path.join(self.apache_config_dir,'webapps','.'.join([self.osx_webapp_name,'plist']))
    
    @property
    def wsgi_file(self):
        wsgi_file_name = '%s.wsgi' % self.project_name
        if self._isosxserver:
            return os.path.join(self.webdata_dir,'WebApps',wsgi_file_name)
        else:
            return os.path.join(self.project_dir,wsgi_file_name)

    @property 
    def settings_file(self):
        return os.path.join(self.settings_dir,'settings.py')

    @property
    def requirements(self):
        if type(self.__requirements) is list:
            return self.__requirements
        else:
            return os.path.join(self.project_dir,self.__requirements)
    
    @requirements.setter
    def requirements(self, value):
        self.__requirements = value

    @requirements.setter
    def apache_custom_config(self, cc_dict={}):
        if type(cc_dict) is dict:
            self.apache_aliases = cc_dict.get('APACHE_ALIAS',[])
            self.apache_protected_locations = cc_dict.get('APACHE_PROTECTED_MEDIA_LOC',[])
    

    def prompt(self):
        while True:
            Colored.echo("[1] www user" "(if you plan to run both non-secure(http) and secure(https))",'purple')
            Colored.echo("[2] create a user %s and group %s" % (self.process_user,self.process_group),'purple')  
            resp = Colored.question('Please Choose',type=int,require=True,values=[1,2])
            if resp == 2:
                if not Util.create_process_user_and_group(self.process_user,self.process_group):
                    if Colored.question('There was a problem creating the user, run as www instead?',type=bool):
                        self.process_user = 'www'
                        self.process_group = 'www'
                        break
                    else:
                        raise
                else:
                    Colored.echo("please choose [1] to run securly (https) or [2] to run on an insecure site(http) ",'purple')
                    self.sslPolicy = Colored.question('Please Choose',type=int,require=True,values=[1,2]) is 1 and 1 or 3
                    print self.sslPolicy
                    break 
            else:
                self.process_user = 'www'
                self.process_group = 'www'
                break

        while True:
            self.virtualenv_path = Colored.question('Where should we install the Virtual Environment ',type=dir,default=self.apache_sites_dir,require=True)
            if Colored.question('  Create env at this path %s ' % self.virtualenv_dir ,type=bool,color='purple'):
                break
    
        self.run_on_subpath = Colored.question('Would you like to run on the subpath "/%s"' % self.apache_subpath ,bool)
        self.server_host_name = Colored.question('Enter the FQDN this will run on ',type=str,default=self.server_host_name,require=True)
        print self.server_host_name

        from getpass import getpass
        self.admin_name = Colored.question('Enter the username for the Django superuser',str)
        self.user_email = Colored.question('email address',str)

        while True:
            self.user_pass = getpass('Password:')
            confirm = getpass('Confirm Password:')
            if not self.user_pass == confirm:
                print "Passwords did not match:"
            else:
                break
        
        for i in self.custom_questions:
            key,qst,typ,dft,req,val = i
            resp = Colored.question(qst,typ,dft,req,val)
            self.modified_settings[key] = resp

        print self.modified_settings


class DjangoApp(object):
    class InstallError(Exception):
        '''Exception to throw if a DjangoApp process fails'''
        pass

    def __init__(self,virtualenv,install_settings):
        if not isinstance(virtualenv, VirtualEnv):
             raise TypeError("Not a virtual environment")
        
        if not isinstance(install_settings, DjangoInstallSettings):
             raise TypeError("Not a Settings object")

        self.settings = install_settings
        self.virtualenv = virtualenv       
        self.name = self.settings.project_name
        self.app_diffsettings={}

        sys.path.append(self.settings.project_dir)
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', '%s.settings' % self.name)
        
    @property
    def settings_py(self):
        return self.settings.settings_file

    @property
    def manage_py(self):
        return os.path.join(self.settings.project_dir,'manage.py')

    @property
    def media_root(self):
        return self.app_diffsettings.get('MEDIA_ROOT',None)

    @property
    def media_url(self):
        return self.app_diffsettings.get('MEDIA_URL',None)

    @property
    def static_root(self):
        return self.app_diffsettings.get('STATIC_ROOT',None)

    @property
    def static_url(self):
        return self.app_diffsettings.get('STATIC_URL')

    def superuser_command(self):
        from django.contrib.auth.models import User
        try:
            User.objects.create_superuser(self.settings.admin_name, self.settings.user_email, self.settings.user_pass)
        except Exception,e:
            print "A super user has already been created, skipping"

    def refresh_dj_settings(self):
        if os.path.exists(self.settings_py +'c'):
            try:
                os.remove(self.settings_py +'c') 
            except Exception,e:
                rm_cmd = ['sudo','rm',self.settings_py +'c'];
                subprocess.check_call(rm_cmd)

        _settings = subprocess.check_output([self.virtualenv.python,self.manage_py,'diffsettings'])
        _settings = _settings.split('\n')
        for _setting in _settings:
            try:
                s_key = _setting.split('=')[0].strip(' ')
                s_value = _setting.split('=')[1].strip('\'"# ')
                self.app_diffsettings[s_key] = s_value
            except IndexError,e:
                print "error handling setting %s" % _setting



    def get_dj_setting(self,key):
        # django holds on to settings so remove the compiled settings file
        if os.path.exists(self.settings_py +'c'):
            os.remove(self.settings_py +'c') 

        _settings = subprocess.check_output([self.virtualenv.python,self.manage_py,'diffsettings'])
        _settings = _settings.split('\n')
        for _setting in _settings:
            if key in _setting :
                return _setting.split('=')[1].strip('\'"# ')


    def install(self):
        self.virtualenv.create()

        try:
            command = ['git','clone','-b',self.settings.git_branch,self.settings.git_repo,self.settings.project_dir]
            subprocess.check_call(command)
        except:
            print "Could not download repo"


        self.virtualenv.install_packages(self.settings.requirements)
        
        self.configure_django_settings()

        # now that everything is installed and configured
        # we should be able to import things
        from django.core.management import call_command
        from django.contrib.auth.models import User

        call_command('syncdb', interactive=False)
        call_command('migrate')
        call_command('collectstatic',interactive=False)
        self.superuser_command()

        self.configure_apache_components()
        self.set_permissions()

    def configure_django_settings(self):
        '''handle the locating and manipulating of the settings.py file'''
        settings_template = None
        search_for = os.path.join(self.settings.settings_dir,'*settings*.py')

        from glob import glob
        for name in glob(search_for):
            if not name == self.settings.settings_file:
                settings_template = name
                break
        
        if not settings_template: 
            raise DjangoApp.Error("could not find settings file, cannot continue...")

        DjangoConfigFile.copy(settings_template,self.settings.settings_file)

        if self.settings.run_on_subpath:
            self.refresh_dj_settings()

            SP = self.settings.apache_subpath
            media_url = self.media_url[1:] if self.media_url.startswith('/') else self.media_url
            self.settings.modified_settings['MEDIA_URL'] = os.path.join('/',SP,media_url,'')
            # if not self.settings.modified_settings.get('STATIC_URL',None):
            static_url = self.static_url[1:] if self.static_url.startswith('/') else self.static_url
            self.settings.modified_settings['STATIC_URL'] = os.path.join('/',SP,static_url,'')

        DjangoConfigFile(self.settings.settings_file).edit_settings_py(self.settings.modified_settings)

    def configure_apache_components(self):
        self.refresh_dj_settings()
        for index,item  in enumerate(self.settings.apache_aliases):
            if type(item) is tuple:
                alias,path = item
                # if both look like paths add them 
                if '/' in alias and '/' in path:
                    self.settings.apache_aliases[index] = item
                else:
                    alias = get_dj_setting(alias) 
                    path = get_dj_setting(path)
                    if alias and path:
                        self.settings.apache_aliases[index] = (alias,path)
            elif item in ['MEDIA_URL','MEDIA_ROOT']:
                self.settings.apache_aliases[index] = (self.media_url,self.media_root)
        
        self.settings.apache_aliases.append((self.static_url,self.static_root))
        
        if self.settings.apache_protected_locations:
            media_url = self.media_url
            for i,loc in enumerate(self.settings.apache_protected_locations):
                self.settings.apache_protected_locations[i] = (os.path.join(media_url,loc))


        DjangoConfigFile(self.settings.apache_config_file).write_apache_conf(self.settings)
        DjangoConfigFile(self.settings.wsgi_file).write_wsgi(self.settings)
        if self.settings._isosxserver:
            DjangoConfigFile(self.settings.osx_webapp_plist_file).write_webapp_plist(self.settings)

        return True

    def set_permissions(self):
        print "Setting permission on web application files"
        mod_perms = [
                    (self.settings.settings_file,0700),
                    (self.media_root,0755),
                    (os.path.join(self.settings.settings_dir,self.settings.project_name+'.db'),0700),
                    ]

        chonw_cmd = ['chown','-R','%s:%s'%(self.settings.process_user,self.settings.process_group),self.virtualenv.path]
        try:
            subprocess.check_call(chonw_cmd)
            for i in self.settings.apache_protected_locations:
                mod_perms.append((os.path.join(self.media_root,i),0700))

            for i in mod_perms:
                path,perm = i
                if os.path.exists(path):
                    os.chmod(path,perm)
        except Exception,e:
            print e

class DjangoConfigFile(object):
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

    class CopyError(Error):
        '''Exception to throw if a DjangoConfigFile copy process fails'''
        pass

    from tempfile import NamedTemporaryFile
    '''Write and Configure files'''
    def __init__(self,file):
        self.file = file
        self.__file_array = []

    @property
    def priviledged_location(self):
        ''' checks if the the directoy is priviledged from the user
            returns True if it is priviledged, indicating the user 
            CANNOT write to the location in the current context,
            and False if the user CAN write to the location
        '''
        # this is a directory, and we're looking for files!
        if os.path.isdir(self.file):
            raise DjangoConfigFile.Error('ERROR: The item specified is a directory ')

        #if file exists return True
        if os.path.isfile(self.file):
            return False if os.access(self.file,os.W_OK) else True
        #else check if there is write priv to directory
        return False if os.access(os.path.dirname(self.file),os.W_OK) else True

    def setting_replace(self,key,replacement):
        for n,i in enumerate(self.__file_array):
            DONT_QUOTE=['os',"'",'"']
            # make sure things that should be quoted, are
            if not type(replacement) is bool:
                if not replacement[0] in DONT_QUOTE:
                    replacement = "'%s'" % replacement

            # get this here to preserve indentation
            key_match = i.split('=')[0]
            if key == key_match.strip():
                substr = '%s = %s\n' % (key_match,replacement)
                self.__file_array[n] = substr
    
    @classmethod
    def copy(self,from_file,to_file):
        try:
            if self.priviledged_location:
                subprocess.call(['sudo','cp','-f','-p',from_file,to_file])
            else:
                copyfile(from_file,to_file)
        except subprocess.CalledProcessError as e:
            raise DjangoConfigFile.PriviledgedProcessError('Error copying file to priviledged location')
        except:
            raise DjangoConfigFile.CopyError('Error copying file')


    def write(self,joint=""):
        tmp_file_string = joint.join(self.__file_array)
        try:
            if self.priviledged_location == True:
                if Colored.question("Write file to priviledged location: %s ? " %self.file,bool,color='red'):
                    tf = NamedTemporaryFile(mode='w+t', delete=False)
                    tf.write(tmp_file_string)
                    tmp_file = tf.name
                    tf.close()
                    subprocess.check_call(['sudo','mv','-i',tmp_file,self.file])
            elif self.priviledged_location == False:
                with open(self.file,'w') as f:
                    f.write(tmp_file_string)
        except subprocess.CalledProcessError:
            raise DjangoConfigFile.PriviledgedProcessError('Error writing to priviledged location')
        except Exception,e:
            raise DjangoConfigFile.WriteError('Error writing the file')
    
    def edit_settings_py(self,settings={}):
        # open the file and get it into memory
        with open(self.file,'r') as f:
            for line in f:
                self.__file_array.append(line)

        # modify all the settings you wish to here
        for key, value in settings.iteritems():
            self.setting_replace(key,value)

        # finish up and write out to the file
        self.write("")

    def write_wsgi(self,settings,):
        # The settings is a DjangoInstallSettings object passed in
        self.__file_array = ["",
            "''' WSGI file created using autoinstall script '''",
            "import os, sys",
            "import site",
            "",
            "VIR_ENV_DIR = '%s'" % settings.virtualenv_dir,
            "",
            "# Use site to load the site-packages directory of our virtualenv",
            "site.addsitedir(os.path.join(VIR_ENV_DIR, 'lib/python2.7/site-packages'))",
            "",
            "# Make sure we have the virtualenv and the Django app itself added to our path",
            "sys.path.append(VIR_ENV_DIR)",
            "sys.path.append(os.path.join(VIR_ENV_DIR, '%s'))" % settings.project_dirname,
            "",
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', '%s.settings')" % settings.settings_dirname,
            "import django.core.handlers.wsgi",
            "application = django.core.handlers.wsgi.WSGIHandler()",
            "",
            ]

        self.write("\n")

    def write_site_fixture(self,settings):
        self.__file_array = []
        self.write("\n")

    def write_apache_conf(self,settings):
        # The settings is a DjangoInstallSettings object passed in

        self.__file_array = ['WSGIScriptAlias /%s %s' % (settings.apache_subpath,settings.wsgi_file)]
        for i in settings.apache_aliases:
            alias,path = i
            self.__file_array.append('Alias %s %s' % (alias,path))

        print settings.process_user
        if not settings.process_user is 'www':
            self.__file_array.extend([
                'WSGIDaemonProcess %s user=%s group=%s' % (settings.project_name,settings.process_user,settings.process_group),
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

    def write_webapp_plist(self,settings):
        name = os.path.splitext(os.path.basename(settings.osx_webapp_plist_file))[:1][0]        
        plist={
        'displayName':settings.project_description,
        'includeFiles':[settings.apache_config_file],
        'installationIndicatorFilePath':settings.wsgi_file,
        'name':settings.osx_webapp_name,
        'requiredModuleNames':['wsgi_module',],
        'sslPolicy':settings.sslPolicy,
        }

        plist_string = writePlistToString(plist)
        self.__file_array.append(plist_string)
        self.write("")

class DSRecordError(Exception):
        '''Exception to throw if DSRecord process fails'''
        pass

class DSRecord(object):
    ''' work with Directory Service, add user and groups
        create an authorized object do

        credentials = DSRecord.credentials('username','password')
        ds = DSRecord(credentials)
        user = DSRecord.user('username','uid','password'...)
        ds.add(user)
    '''

    def __init__(self,credentials=None,node='.'):
        self.credentials = credentials
        self.node = node
        self.id_search_start = 1025
        self.id_search_max = 2000
        self.__dscl_base = None
                
    class credentials:
        def __init__(self,admin=None,password=None):
            self.admin=admin
            self.password=password
    
    class user:
        def __init__(self,name,uid=None,password='*',gid=20,):
            self.name = name
            self.uid = uid
            self.realname = name 
            self.password = password
            self.primary_gid = gid
            self.shell = '/bin/bash'
            self.home = '/dev/null'
               
    class group:
        def __init__(self,name,gid=None):
            self.name = name
            self.gid = gid
    
    def ldap_user_setup(self,host):
        self.node = os.path.join('/LDAPv3/',host)

    def system_user_setup(self):
        self.id_search_start = 400
        self.id_search_max = 500
        self.node = '.'
        
    def dscl(self,args=[]):
        __dscl = ['dscl']
        
        if self.credentials and self.credentials.admin and self.credentials.password:
            __dscl.extend(['-u',admin,'-P',password])
        elif 'create' in self.__dscl_base or 'create' in args:
            __dscl.insert(0,'sudo')
        
        __dscl.extend([self.node]) 
        if self.__dscl_base and not args == self.__dscl_base:
            __dscl.extend(self.__dscl_base)
        
        __dscl.extend(args)
        
        try:
            return subprocess.check_output(__dscl)
        except:
            raise
    
    def get_valid_id(self,path,key):
        list_cmd = ['list','/%s' % path ,key]
        vid = self.id_search_start
        vids = self.dscl(list_cmd)
        arr = []
        for i in vids:
            x = i.split()
            if x and len(x) > 1: arr.append(x[1])

        while vid < self.id_search_max:
            if str(vid) in arr:
                vid += 1
            else:
                return str(vid)
        raise DSRecordError('could not a valid unique id in range')
    
    def add(self,record,update=False):
        try:
            if isinstance(record,DSRecord.user): 
                import pwd
                self.__dscl_base = ['create','/Users/%s' % record.name]
                try:
                    err_msg = 'There was a problem creating the %s user record' % record.name
                    uid = pwd.getpwnam(record.name).pw_uid
                    record.uid = record.uid or uid
                    print 'User "%s" already exists' % record.name
                except:
                    print 'Creating user "%s"' % record.name
                    record.uid = record.uid or self.get_valid_id('Users','UniqueID')
                    self.dscl()
                    update = True
                
                if update:
                    print 'Updating user record'
                    err_msg = 'There was a problem updating the "%s" user record' % record.name
                    self.dscl(['RealName',record.name])
                    self.dscl(['UniqueID',str(record.uid)])
                    self.dscl(['passwd',record.password])
                    self.dscl(['UserShell',record.shell]) 
                    self.dscl(['NFSHomeDirectory',record.home])
                    self.dscl(['PrimaryGroupID',str(record.primary_gid)])
                
            elif isinstance(record,DSRecord.group):
                import grp
                err_msg = 'There was a problem creating the "%s" group record' % record.name
                try:
                    gid = grp.getgrnam(record.name).gr_gid
                    record.gid = record.gid or gid
                    print 'group "%s" already exists' % record.name
                except:
                    update = True
                    
                if update:
                    err_msg = 'There was a problem updating the "%s" group record' % record.name
                    if not record.gid:group.gid = self.get_valid_id('Groups','PrimaryGroupID')
                    grp_cmd = ['dseditgroup','-o','create','-r',record.name,'-i',str(record.gid),'-n','.']
                    admin = self.credentials.admin
                    password = self.credentials.password
                    if admin and password:
                        grp_cmd.extend(['-u',admin,'-P',password])
                    grp_cmd.extend([name])  
                    subprocess.check_output(grp_cmd)
            
            print ' Successfully added record' if update else '  skipping...'

        except DSRecordError as e:
            raise e
        except:
            raise DSRecordError(err_msg)
        finally:
            self.__dscl_base = []

class Util:
    class Error(Exception):
        '''Exception to throw if util process fails'''
        pass

    @classmethod
    def webappctl(self,command,webapp,vhost=None):
        wac = '/Applications/Server.app/Contents/ServerRoot/usr/sbin/webappctl'
        try:
            webapp_cmd = ['sudo','wac',command,webapp,]
            if vhost:
                webapp_cmd.extend(['-',vhost])

            subprocess.check_call(webapp_cmd)    
        except subprocess.CalledProcessError:
            raise Util.Error('Could not start webapp')

    @classmethod
    def serveradmin(self,module,value):
        ssad = '/Applications/Server.app/Contents/ServerRoot/usr/sbin/serveradmin'
        default_path = '/Library/Server/Web/Data'
        try:
            ssad_command = ['sudo',ssad,'settings',':'.join([module,value])]
            results = subprocess.check_output(ssad_command)    
            string = results.split('=')[1].strip().strip('\"')
            if not string in ('_empty_dictionary',):
                return string
        except Exception, e:
            pass
        return default_path

    @classmethod
    def create_process_user_and_group(self,process_user,process_group):
        try:
            user = DSRecord.user(process_user)
            group = DSRecord.group(process_group)
            record = DSRecord()
            record.system_user_setup()
            record.add(group)
            user.primary_gid = group.gid
            record.add(user)
            return True
        except Exception,e:
            return False

class Colored:
    @classmethod
    def ansii_color_str(self,message,color=None):
        if color in ('red','alert'):
            c_val = '31';
        elif color in ('green','attention'):
            c_val = '32';
        elif color in ('yellow','warn'):
            c_val = '33';
        elif color in ('blue','question'):
            c_val = '34';
        elif color in ('purple','info'):
            c_val = '35';
        elif color in ('cyan','notice'):
            c_val = '36';
        elif color in ('bold','prompt'):
            c_val = '37';
        else:
            c_val = '0'

        attr = ['1']
        attr.append(c_val)
        color_string = '\x1b[%sm%s\x1b[m' % (';'.join(attr),message)
        return color_string

    @classmethod
    def read(self,message,color=None,type=str):
        string = raw_input(Colored.ansii_color_str(message,color));
        if type is bool:
            if string in ('Y','y','Yes','yes','YES'):
                return True
            elif string in ('N','n','No','no','NO'):
                return False
        else:
            return string
    
    @classmethod
    def echo(self,message,color=None):
        print(self.ansii_color_str(message,color));

    @classmethod
    def question(self,message,type=str,default={},require=True,values=[],color='question'):
        while True:
            prompt = message
            if type == bool:
                prompt = message + '[(Y)es/(N)o]'
            elif default:
                prompt = message + '[%s]'% default

            prompt = prompt + ': '
            ret = self.read(prompt,color=color,type=type)
            if type == bool:
                if ret in (True,False):
                    break
                else:
                    self.echo("Please answer Yes or No",'alert')

            elif type == file:
                if not ret and default:
                    ret = default
                if require and not os.path.exists(ret):
                    self.echo("There's No file at that path",'alert')
                else:
                    break

            elif type == dir:
                if not ret and default:
                    ret = default
                if require and not os.path.isdir(ret):
                    self.echo("There's No directory at that path",'alert')
                else:
                    break

            elif type == int:
                try:
                    ret = int(ret)
                    if values and not ret in values:
                        raise ValueError()
                    break
                except ValueError:
                    self.echo("please choose form these values %s" % values ,'alert')
            else:  # type is string
                if default and not ret:
                    ret = default
                if require and not ret:
                    self.echo("There was an empty response",'alert')
                else:
                    break
        return ret


def main(argv):
    global __defined_settings   
    install_settings = DjangoInstallSettings(__defined_settings['PROJECT_NAME'],__defined_settings)

    c = Colored
    c.echo("##############################################################################",'red')
    c.echo("################           django webapp installer          ##################",'red')
    c.echo("##############################################################################",'red')
    
    install_settings.prompt()
    venv = VirtualEnv(install_settings.virtualenv_path,
                        __defined_settings['PROJECT_NAME'])

    app = DjangoApp(venv,install_settings)
    app.install()

# @atexit.register
def goodbye():
    print "\nCanceling the Auto install script."

if __name__ == "__main__":
    if os.geteuid() != 0:
        Colored.echo('Script must run as root, relaunching','red')
        os.execvp("sudo", ["sudo"] + sys.argv)
    else:        
        try:
            main(sys.argv)
        except KeyboardInterrupt:
            goodbye()
        