#!/usr/bin/env python

import os
import sys
import subprocess
import imp
import site
import atexit

from shutil import copyfile, move
from tempfile import NamedTemporaryFile

__defined_settings = {
'PROJECT_NAME':'printerinstaller',
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
        ]

'CUSTOM_APACE_CONFIG':{
# only STATIC_URL is aliased by default, include any others here
    'ALIAS':['MEDIA_ROOT',''],
# reletavive to MEDIA_URL, allow uploading files here, but prevent downloading from...
    'PROTECTED_MEDIA_LOC':['private'],
}

class VirtualEnvError(Exception):
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
                    
    def create(self):
        if not self.created:
            self.check_reqs()
            try:
                subprocess.check_call(['virtualenv',self.path],stdout=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                raise VirtualEnvError("There was a problem creating the Virtual Environment, exiting(%d)..." % e.returncode)
        else:
            print "Environment already exists, activating"
        self.activate()

    def activate(self):
        if not self.created:
            self.create()
            
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
                if  os.path.isfile(requirements):
                    pip_cmd.append('-r')
                    pip_cmd.append(requirements)
                else:
                    raise VirtualEnvError("Error: Requirements not properly specified!")
          
            subprocess.check_call(pip_cmd)
        except ValueError:
            print "A valid requirements file was not found"
        except subprocess.CalledProcessError:
            pass     

class DjangoInstallSettings(object):
    __isosxserver = True if not os.path.exists('/Applications/Server.app') else False

    def __init__(self,project_name,defaults={}): 
        self.project_name = defaults.get('PROJECT_NAME',project_name)
        self.project_dirname = defaults.get('PROJECT_DIRNAME',project_name)
        self.settings_dirname = defaults.get('SETTINGS_DIRNAME',project_name)
        
        self.custom_questions = defaults.get('CUSTOM_QUESTIONS',None)
        self.modified_settings = defaults.get('MODIFIED-SETTINGS',{})

        self.process_user = defaults.get('PROCESS_USER',project_name)
        self.process_group = defaults.get('PROCESS_GROUP',project_name)

        self.admin_name = 'admin'
        self.user_email = 'admin@example.com'
        self.user_pass  = 'password'

        self.run_on_subpath = False
        self.apache_subpath = defaults.get('APACHE_SUBPATH',project_name)
        self.apache_aliases = []
        self.apache_protected_locations = []
        self.apache_custom_config = defaults.get('CUSTOM_APACE_CONFIG',{})

        self.run_on_osxserver = True if self.__isosxserver else False

        self.__requirements = defaults.get('REQUIREMENTS',os.path.join('setup','requirements.txt'))

        self.git_repo = defaults.get('GIT-REPO',None)
        self.git_branch = defaults.get('GIT-BRANCH','master')
        if not self.git_repo:
            raise ValueError

        self.webdata_dir = Util.serveradmin('web','dataLocation') if self.__isosxserver else '/usr/local/www'


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
    def osx_site_dir(self):
        return os.path.join(self.webdata_dir,'Sites')

    @property 
    def osx_webapp_dir(self):
        return os.path.join(self.webdata_dir,'WebApps')

    @property 
    def wsgi_file(self):
        wsgi_file_name = '%s.wsgi' % self.project_name
        if self.run_on_osxserver:
            return os.path.join(self.osx_webapp_dir,'WebApps',wsgi_file_name)
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

    def question(self,message,type=str,default={},require=True,values=[]):
        c = Colored
        while True:
            prompt = message
            if type == bool:
                prompt = message + '[ (Y)es/(N)o ]'
            elif default:
                prompt = message + '[%s]'% default

            prompt = prompt + ': '
            ret = c.read(prompt,'question')
            if type == bool:
                if ret in (True,False):
                    break
                else:
                    c.echo("Please answer Yes or No",'alert')

            elif type == file:
                if not ret and default:
                    ret = default
                if require and not os.path.exists(ret):
                    c.echo("There's No file at that path",'alert')
                else:
                    break

            elif type == int:
                try:
                    ret = int(ret)
                    if not ret in values:
                        raise ValueError()
                    break
                except ValueError:
                    c.echo("please choose form these values %s" % values ,'alert')
            else:  # type is string
                if not ret == '' and require:
                    break
                elif default:
                    ret = default
                else:
                    c.echo("There was an empty response",'alert')
        return ret


    def prompt(self):
        self.virtualenv_path = self.question('Where should we install the Virtual Environment',file,self.webdata_dir+'/Sites',True)
        # self.question('  Confirm install path :%s' % self.virtualenv_path ,bool)

        c = Colored
        c.echo("[1] www user" "(if you plan to run on both http(80) and https(443))",'purple')
        c.echo("[2] create a user %s and group %s" % (self.process_user,self.process_group),'purple')  
        resp = self.question('Please Choose',int,None,False,[1,2])
        if not resp == 1:
            self.process_user = 'www'
            self.process_group = 'www'

        if self.__isosxserver:
            self.run_on_osxserver = self.question('Do you want to run as OSX WebApp',bool)
        
        self.run_on_subpath = self.question('Would you like to run on the subpath "/%s"' % self.apache_subpath ,bool)
        
        # from getpass import getpass
        # self.admin_name = self.question('Enter the username for the Apps superuser',str)
        # self.user_email = self.question('email address',str)

        # while True:
        #     self.user_pass = getpass('Password:')
        #     confirm = getpass('Confirm Password:')
        #     if not self.user_pass == confirm:
        #         print "Passwords did not match:"
        #     else:
        #         break
        for i in self.custom_questions:
            key,qst,typ,dft,req,val = i
            resp = self.question(qst,typ,dft,req,val)
            self.modified_settings[key] = resp

        print self.modified_settings


class DjangoAppError(Exception):
    '''Exception to throw if a DjangoApp process fails'''
    pass

class DjangoApp(object):    
    def __init__(self,virtualenv,install_settings):
        if not isinstance(virtualenv, VirtualEnv):
             raise TypeError("Not a virtual environment")
        
        if not isinstance(install_settings, DjangoInstallSettings):
             raise TypeError("Not a Settings object")

        self.settings = install_settings
        self.virtualenv = virtualenv       
        self.name = self.settings.project_name
        
        sys.path.append(self.settings.project_dir)
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', '%s.settings' % self.name)
        
    @property
    def media_root(self):
        return self.get_dj_setting('MEDIA_ROOT')

    @property
    def media_url(self):
        return self.get_dj_setting('MEDIA_URL')

    @property
    def static_root(self):
        return self.get_dj_setting('STATIC_ROOT')

    @property
    def static_url(self):
        return self.get_dj_setting('STATIC_URL')

    def install(self):
        if not self.virtualenv.create():
            self.virtualenv.create()
        
        try:
            command = ['git','clone','-b',self.settings.git_branch,self.settings.git_repo,self.settings.project_dir]
            print " ".join(command)
            subprocess.check_call(command)
        except:
            print "Could not download repo"

        # self.virtualenv.install_packages(self.settings.requirements)
        self.configure()

        # now that everything is installed and configured
        # we should be able to import things
        # from django.core.management import call_command
        # from django.contrib.auth.models import User

        # call_command('syncdb', interactive=False)
        # call_command('migrate')
        # call_command('collectstatic',interactive=False)
        # self.superuser_command()

    def superuser_command(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser(self.settings.admin_name, self.settings.user_email, self.settings.user_pass)

    def get_dj_setting(self,key):
        from printerinstaller import settings
        return getattr(settings,key,None)

    def configure(self):
        '''handle the locating and manipulating of the settings.py file'''
        settings_template = None
        search_for = os.path.join(self.settings.settings_dir,'*settings*.py')

        from glob import glob
        for name in glob(search_for):
            if not name == self.settings.settings_file:
                settings_template = name
                break
        
        if not settings_template:
            print "could not find settings file, cannot continue..."
            exit(1)

        copyfile(settings_template,self.settings.settings_file)

        if self.settings.run_on_subpath:
            SP = self.settings.apache_subpath
            # if not self.settings.modified_settings.get('MEDIA_URL',None):
            media_url = self.media_url[1:] if self.media_url.startswith('/') else self.media_url
            self.settings.modified_settings['MEDIA_URL'] = os.path.join('/',SP,media_url,'')
    
            # if not self.settings.modified_settings.get('STATIC_URL',None):
            static_url = self.static_url[1:] if self.static_url.startswith('/') else self.static_url
            self.settings.modified_settings['STATIC_URL'] = os.path.join('/',SP,static_url,'')

        print self.settings.modified_settings
        FileConfig(self.settings.settings_file).edit_settings_py(self.settings.modified_settings)

        #TODO: setup apache config settings



class FileConfig(object):
    class Error(Exception):
        '''Exception to throw if a FileConfig process fails'''
        pass

    from tempfile import NamedTemporaryFile
    '''Write and Configure files'''
    def __init__(self,file):
        self.file = file
        self.__file_array = []

    def setting_replace(self,key,replacement):
        for n,i in enumerate(self.__file_array):
            DONT_QUOTE=['os',"'",'"']
            # make sure things that should be quoted are
            if not type(replacement) is bool:
                if not replacement[0] in DONT_QUOTE:
                    replacement = "'%s'" % replacement

            # get this here to preserve spaces/tabs in the file's format
            key_match = i.split('=')[0]
            if key == key_match.strip():
                substr = '%s = %s\n' % (key_match,replacement)

                print 'replacing ' + substr
                self.__file_array[n] = substr

    def write(self,joint="",protected_location=False):
        tmp_file_string = joint.join(self.__file_array)
        if protected_location:
            f = NamedTemporaryFile(mode='w+t', delete=False)
            f.write(tmp_file_string)
            file_name = f.name
            f.close()
            subprocess.call(['sudo','mv','-i',file_name,self.file])
        else:
            with open(self.file,'w') as f:
                f.write(tmp_file_string)
    
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

    def write_wsgi2(self,settings):
        # The settings is a DjangoInstallSettings object passed in
        self.__file_array = ["",
            "''' WSGI file created using autoinstall script '''",
            "import os, sys",
            "import site",
            "",
            "VIR_ENV_DIR = %s" % settings.virtualenv_dir,
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

        self.write("\n",protected_location=True)

    def write_site_fixture(self,settings):
        self.__file_array = []
        self.write("\n")

    def write_apache_conf(self,settings):
        # The settings is a DjangoInstallSettings object passed in

        self.__file_array = ['WSGIScriptAlias %s %s' % (settings.wsgi_file),]
        
        for i in settings.apache_aliases:
            alias,path = i
            self.__file_array.extend(['Alias %s %s' % (alias,path)])

        if not settings.process_user = 'www':
            self.__file_array.extend([
                'WSGIDaemonProcess %s user=%s group=%s' %(settings.project_name,settings.process_user,settings.process_group),
                '<Location /%s>' % settings.apache_subpath,
                '   WSGIProcessGroup %s' % settings.project_name,
                '    WSGIApplicationGroup %{GLOBAL}',
                '    Order deny,allow',
                '    Allow from all',
                '</Location>',
                ])
        for i in settings.apache_protected_locations
        self.write("\n",protected_location=True)

    def write_webapp_plist(self,settings):
        self.__file_array = []
        self.write("\n",protected_location=True)


class DSRecord(object):
    ''' work with Directory Service, add user and groups
        create an authorized object do

        credentials = DSRecord.credentials('username','password')
        DSRecord(credentials)
        user = DSRecord.user('username','uid','password'...)
        DSRecord.add(user)
    '''
    def __init__(self,credentials=None,node='.'):
        self.credentials = credentials
        self.node = node
        self.id_search_start = 1025
        self.id_search_max = 2000
        self.__dscl_base = None
        
    class Error(Exception):
        pass
        
    class credentials:
        def __init__(self,admin,password):
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
            
    def system_user_setup(self):
        self.id_search_start = 400
        self.id_search_max = 500
        self.node = '.'
        
    def dscl(self,args=[]):
        __dscl = ['dscl']
        admin = self.credentials.admin
        password = self.credentials.password
        
        if admin and password:
            __dscl.extend(['-u',admin,'-P',password])
        __dscl.extend([self.node])
        
        if self.__dscl_base and not args == self.__dscl_base:
            __dscl.extend(self.__dscl_base)
        
        __dscl.extend(args)
        
        try:
            return subprocess.check_output(__dscl)
        except:
            raise DSRecord.Error('Problem running the dscl command')
    
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
        return None
    
    def add(self,record,update=False):
        if isinstance(record,DSRecord.user): 
            import pwd
            self.__dscl_base = ['create','/Users/%s' % record.name]
            try:
                uid = pwd.getpwnam(record.name).pw_uid
                if not record.uid:record.uid=uid
                print 'user %s already exists' % record.name
            except:
                if not record.uid:record.uid = self.get_valid_id('Users','UniqueID')
                self.dscl()
                update = True
            
            if update:
                print 'updating user record...'
                self.dscl(['RealName',record.name])
                self.dscl(['UniqueID',str(record.uid)])
                self.dscl(['passwd',record.password])
                self.dscl(['UserShell',record.shell]) 
                self.dscl(['NFSHomeDirectory',record.home])
                self.dscl(['PrimaryGroupID',str(record.primary_gid)])
                
            self.__dscl_base = []
            
        elif isinstance(record,DSRecord.group):
            import grp
            try:
                gid = grp.getgrnam(record.name).gr_gid
                if not record.gid:record.gid=gid
                print 'group %s already exists' % record.name
            except:
                update = True
                
            if update:
                if not record.gid:group.gid = self.get_valid_id('Groups','PrimaryGroupID')
                grp_cmd = ['dseditgroup','-o','create','-r',record.name,'-i',str(record.gid),'-n','.']
                admin = self.credentials.admin
                password = self.credentials.password
                if admin and password:
                    grp_cmd.extend(['-u',admin,'-P',password])
                grp_cmd.extend([name])  
                subprocess.check_output(grp_cmd)

class Util:
    class Error(Exception):
        '''Exception to throw if util process fails'''
        pass

    @classmethod
    def serveradmin(Util,module,value):
        ssad = '/Applications/Server.app/Contents/ServerRoot/usr/sbin/serveradmin'
        default_path = '/Library/Server/Web/Data'
        try:
            results = subprocess.check_output([ssad,'settings',module + ':' + value],stdout=subprocess.PIPE)    
            string = results.split('=')[1].strip().strip('\"')
            if not string in ('_empty_dictionary',):
                return string
        except:
            pass
        return default_path

    @classmethod
    def create_process_user_and_group(Util,process_user,process_group):
        group = DSRecord.group(process_group)
        user = DSRecord.user(process_user)
        record = DSRecord()
        record.system_user_setup()
        record.add(group)
        user.primary_gid = group.gid
        record.add(user)

class Colored:
    @classmethod
    def ansii_color_str(Colored,message,color=None):
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
    def read(Colored,message,color=None):
        str = raw_input(Colored.ansii_color_str(message,color));
        if str in ('Y','y','Yes','yes','YES'):
            return True
        elif str in ('N','n','No','no','NO'):
            return False
        return str
    
    @classmethod
    def echo(Colored,message,color=None):
        print(Colored.ansii_color_str(message,color));


def main(argv):
    global __defined_settings   
    install_settings = DjangoInstallSettings(__defined_settings['PROJECT_NAME'],__defined_settings)

    c = Colored
    c.echo("##########################################################################",'red')
    c.echo("##############           django webapp installer          ################",'red')
    c.echo("##########################################################################",'red')
    
    install_settings.prompt()
    venv = VirtualEnv(install_settings.virtualenv_path,
                        __defined_settings['PROJECT_NAME'])
    venv.activate()
    
    app = DjangoApp(venv,install_settings)
    app.install()

    # FileConfig('/tmp/ex.wsgi').write_wsgi2(install_settings)
    # FileConfig('/tmp/ex.settings.py').edit_settings(install_settings)

@atexit.register
def goodbye():
    print "\nExiting the Auto install script."

if __name__ == "__main__":
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        pass
        