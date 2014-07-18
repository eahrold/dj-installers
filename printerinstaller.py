#!/usr/bin/env python

import os
import sys
import subprocess
import imp

from shutil import copy, copy2, copyfile

settings = {
'project_name':'',
'git-repo':'',
'git-branch':'',

}

class Settings:
    def prompt(self,message,type=str,default={},require=False,values=[]):
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
                if not ret == '':
                    break
                elif default:
                    ret = default
                else:
                    c.echo("There was an empty response",'alert')

        return ret


    def __init__(self,project_name,defaults={}): 
        c = Colored
        self.project_name = getattr(defaults,'PROJECT_NAME',project_name)
        self.settings_dirname = getattr(defaults,'SETTINGS_DIRNAME',project_name)
        self.user = getattr(defaults,'USER_NAME',project_name)
        self.group = getattr(defaults,'GROUP_NAME',project_name)
        
        c.echo("[1] www user" "(if you plan to run on both http(80) and https(443))",'purple')
        c.echo("[2] create a user %s and group %s" % (self.user,self.group),'purple')  
        resp = self.prompt('Please Choose',int,None,False,[1,2])
        if not resp == 1:
            self.user = 'www'
            self.group = 'www'

        webDataLocal = '/usr/local/www'
        if os.path.exists('/Applications/Server.app'):
            self.run_on_osxserver = self.prompt('Do you want to run as OSX WebApp',bool)
            webDataLocal = Util.serveradmin('web','dataLocation')
        
        self.virtualenv = self.prompt('Where should we install the Virtual Environment',file,webDataLocal,True)
        
        

class VirtualEnv(object):
    __venv_path = []

    def __init__(self,path,name):
        self.__name = name + '_env'
        self.__path = os.path.join(path,self.__name)
        self.__created = False
        
    @property 
    def virtualenv_path(self):
        return self.__venv_path[0]
    
    @property 
    def pip(self):
        return os.path.join(self.__path,'bin','pip')
    
    @property 
    def python(self):
        return os.path.join(self.__path,'bin','python') 
        
    @property
    def path(self):
        return self.__path

    @property
    def name(self):
        return self.__name
    
    def check_reqs(self):
        if not self.__venv_path:
            try:
                print "Checking on existence of virtualenv"
                self.__venv_path.append(subprocess.check_output(['which','virtualenv']))
            except:
                try:
                    subprocess.check_call(['easy_install', 'virtualenv'])
                    self.check_requs()
                except:
                    print "There was a problem Installing virtualenv"
                    print "Exiting..."
                    exit()
                    
    def create(self):
        self.check_reqs()
        
        if not self.__created:
            try: 
                subprocess.check_call(['virtualenv',self.__path])
                self.__created = True
            except subprocess.CalledProcessError as e:
                print "There was a problem creating the Virtual Environment"
                print "Exiting with status %s..." % e.returncode
                exit(e.returncode)
        else:
            print "Environment already exists, activating"
        self.activate()

    def activate(self):
        activate_file = os.path.join(self.__path,"bin/activate_this.py")
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
                    raise ValueError()
                    
            subprocess.check_call(pip_cmd)
        except ValueError:
            print "A valid requirements file was not found"
        except subprocess.CalledProcessError:
            pass     

class DjangoApp(object):
    def __init__(self,virtualenv,settings):
        if not isinstance(virtualenv, VirtualEnv):
             raise TypeError("Not a virtual environment")
        
        if not isinstance(virtualenv, VirtualEnv):
             raise TypeError("Not a Settings object")

        self.name = settings.project_name
        self.virtualenv = virtualenv #equivelant to the virtual_env path       
        self.settings = settings

        self._path = os.path.join(virtualenv.path,settings.project_name)
        self._settings_dir = os.path.join(self._path,settings.settings_dirname);

        self.__requirements = os.path.join('setup','requirements.txt')
        self.__manage = os.path.join(virtualenv.path,self.name,'manage.py')
        self.__settings_file = os.path.join(self._settings_dir,'settings.py')

    @property 
    def path(self):
        return self._path

    @property 
    def settings_dir(self):
        return self._settings_dir

    @property
    def requirements(self):
        if type(self.__requirements) is list:
            return self.__requirements
        else:
            return os.path.join(self.path,self.__requirements)
    
    @requirements.setter
    def requirements(self, value):
        self.__requirements = value
    

    def install(self,repo,branch='master'):
        self.virtualenv.create()
        try:
            subprocess.check_call(['git','clone','-b',branch,repo,self.path])
        except:
            print "Could not download repo"

        self.virtualenv.install_packages(self.requirements)
        self.configure()
        self.manage(['syncdb'])
        self.manage(['migrate'])
        self.manage(['collectstatic','--noinput'])


        
    def manage(self,args=[]):
        proc_args = [self.virtualenv.python,self.__manage]
        proc_args.extend(args)
        command = " ".join(proc_args)
        try:
            subprocess.check_call(command,shell=True)
        except subprocess.CalledProcessError as e:
            print e

    def configure(self):
        '''This will handle the locating and manipulating of the settings.py file'''
        from glob import glob
        for name in glob(os.path.join(self.settings_dir,'*settings*.py')):
            if not name == self.__settings_file:
                settings_template = name
                break
        
        if not settings_template:
            print "could not find settings file, cannot continue..."
            exit(1)

        copyfile(settings_template,self.__settings_file)




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
    def writeline(f,line=None):
        if line:
            f.write(line +'\n')
        else:
            f.write('\n')

    @classmethod
    def write_wsgi (file_path):
        os.remove(file_path)
        with open(file_path,"wr") as f:
            writeline(f,"''' WSGI file created using autoinstall script '''")
            writeline(f,"import os, sys")
            writeline(f)
            writeline(f,"import site")
            writeline(f)
            writeline(f,"#set the next line to your printerinstaller environment")
            writeline(f,"VIR_ENV_DIR = %s" % DJANGO_WEBAPP_VIR_ENV)
            writeline(f)
            writeline(f,"# Use site to load the site-packages directory of our virtualenv")
            writeline(f,"site.addsitedir(os.path.join(VIR_ENV_DIR, 'lib/python2.7/site-packages'))")
            writeline(f)
            writeline(f,"# Make sure we have the virtualenv and the Django app itself added to our path")
            writeline(f,"sys.path.append(VIR_ENV_DIR)")
            writeline(f,"sys.path.append(os.path.join(VIR_ENV_DIR, '%s'))" % PROJECT_NAME)
            writeline(f)
            writeline(f,"os.environ.setdefault('DJANGO_SETTINGS_MODULE', '%s.settings')" % PROJECT_SETTINGS_DIR)
            writeline(f,"import django.core.handlers.wsgi")
            writeline(f,"application = django.core.handlers.wsgi.WSGIHandler()")




def main():
    c = Colored
    c.echo("##################################################################",'red')
    c.echo("##########         django webapp installer            ############",'red')
    c.echo("##################################################################",'red')
    
    projName = 'printerinstaller'

    settings = Settings(projName)

    repo="https://github.com/eahrold/printerinstaller-server.git"
    
    venv = VirtualEnv(settings.virtualenv,projName)
    app = DjangoApp(venv,settings)

    app.install(repo)
    
    
    
if __name__ == "__main__":
    main()