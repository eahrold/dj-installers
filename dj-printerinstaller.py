#!/usr/bin/env python

import os
import sys
import subprocess
import imp
import site

from shutil import copyfile, move
from tempfile import NamedTemporaryFile

__defined_settings = {
'PROJECT_NAME':'printerinstaller',
'GIT-REPO':'https://github.com/eahrold/printerinstaller-server.git',
'GIT-BRANCH':'master',
'APACHE_SUBPATH':'printers',

'MODIFIED-SETTINGS':{ 
    
},
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
    __isosxserver = True if os.path.exists('/Applications/Server.app') else False

    def __init__(self,project_name,defaults={}): 
        self.virtualenv_path = None

        self.project_name = defaults.get('PROJECT_NAME',project_name)
        self.project_dirname = defaults.get('PROJECT_DIRNAME',project_name)
        self.settings_dirname = defaults.get('SETTINGS_DIRNAME',project_name)

        self.process_user = defaults.get('PROCESS_USER',project_name)
        self.process_group = defaults.get('PROCESS_GROUP',project_name)

        self.admin_name = 'admin'
        self.user_email = 'admin@example.com'
        self.user_pass  = 'password'

        self.run_on_subpath = False
        self.apache_subpath = defaults.get('APACHE_SUBPATH',project_name)
        self.run_on_osxserver = True

        self.__requirements = defaults.get('REQUIREMENTS',os.path.join('setup','requirements.txt'))

        self.git_repo = defaults.get('GIT-REPO',None)
        self.git_branch = defaults.get('GIT-BRANCH','master')

        if not self.git_repo:
            raise ValueError


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
        webDataLocal = Util.serveradmin('web','dataLocation') if self.__isosxserver else '/usr/local/www'

        self.virtualenv_path = self.question('Where should we install the Virtual Environment',file,webDataLocal,True)
        
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

class DjangoAppError(Exception):
    '''Exception to throw if a DjangoApp process fails'''
    pass

class DjangoApp(object):    
    def __init__(self,virtualenv,app_settings):
        if not isinstance(virtualenv, VirtualEnv):
             raise TypeError("Not a virtual environment")
        
        if not isinstance(app_settings, DjangoInstallSettings):
             raise TypeError("Not a Settings object")

        self.settings = app_settings
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

        print "Requirements file" + self.settings.requirements

        self.virtualenv.install_packages(self.settings.requirements)
        self.configure()

        # now that everything is installed and configured
        # we should be able to import things
        from django.core.management import call_command
        from django.contrib.auth.models import User

        call_command('syncdb', interactive=False)
        call_command('migrate')
        call_command('collectstatic',interactive=False)
        self.superuser_command()

    def superuser_command(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser(self.settings.admin_name, self.settings.user_email, self.settings.user_pass)

    def get_dj_setting(self,key):
        from printerinstaller import settings
        return getattr(settings,key,None)

    def configure(self):
        '''handle the locating and manipulating of the settings.py file'''
        settings_template = None
        # print self.media_root
        # print self.media_url
        # print self.static_root
        # print self.static_url

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

class FileConfigError(Exception):
    '''Exception to throw if a FileConfig process fails'''
    pass

class FileConfig(object):
    '''Write and Configure files'''
    def __init__(self,file):
        self.file = file
        self.__file_array = []
        self.__file = None

    def setting_replace(self,key, replacement):
        substr = '%s=%s\n' % (key,replacement)
        for n,i in enumerate(self.__file_array):
            if i.split('=')[0] == key:
                self.__file_array[n] = substr

    def write(self,joint=""):
        tmp_file_string = joint.join(self.__file_array)
        with open(self.file,'w') as f:
            f.write(tmp_file_string)

    def edit_settings(self,settings={}):
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

        self.write("\n")

    def write_site_fixture(self,settings):
        with open(self.file,"wr") as self.__file:
            pass

    def write_apache_conf(self,settings):
        with open(self.file,"wr") as self.__file:
            pass


class UtilError(Exception):
    '''Exception to throw if util process fails'''
    pass

class Util:
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
        __user_kind = '__user_kind'
        __group_kind = '__group_kind'
        def dscl(args):
            __dscl = ['dscl','.']
            __dscl.extend(args)
            return subprocess.check_output(__dscl)
        def get_valid_id(kind):
            vid = 400
            if kind == Util.__user_kind:
                vids = dscl('list /Groups PrimaryGroupID'.split()).split('\n')
            else:
                vids = dscl('list /Groups PrimaryGroupID'.split()).split('\n')
            arr = []
            for i in vids:
                x = i.split()
                if x: arr.append(x[1])

            while vid < 500:
                if str(vid) in arr:
                    vid += 1
                else:
                    return vid
            
            return None

        def check_if_exists(name,kind):
            if not kind in [__user_kind,__group_kind]: raise ValueError("incorrect spec")
            import pwd,grp
            if kind == Util.__user_kind:
                cmd = pwd.getpwnam
            else:
                cmd = grp.getgrnam

        if not check_if_exists(process_user,Util.__user_kind):
            uid = get_valid_id(Util.__user_kind)

        def check_if_exists(name,kind):
            if not kind in [__user_kind,__group_kind]: raise ValueError("incorrect spec")
            import pwd,grp
            if kind == __user_kind:
                cmd = pwd.getpwnam
            else:
                cmd = grp.getgrnam

        if check_if_exists(process_user,'user'):
            uid = get_valid_id('user')
            # dscl(['-create','/Users/%s'])

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
    venv = VirtualEnv(install_settings.virtualenv_path,__defined_settings['PROJECT_NAME'])
    venv.activate()
    
    app = DjangoApp(venv,install_settings)
    app.install()

    # FileConfig('/tmp/ex.wsgi').write_wsgi2(install_settings)
    # FileConfig('/tmp/ex.settings.py').edit_settings(install_settings)
    
if __name__ == "__main__":
    main(sys.argv)