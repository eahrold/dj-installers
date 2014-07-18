#!/usr/bin/env python
import os
import subprocess

class InstallSettings():
	def __init__(self):
		self.PROJECT_NAME='printerinstaller'
		self.GIT_REPO="https://github.com/eahrold/printerinstaller-server.git"
		self.GIT_BRANCH="master"

		self.OSX_WEBAPP_PLIST="edu.loyno.smc.printerinstaller.webapp.plist"
		self.APACHE_SUBPATH="printers"

		## you only need to set one of the following two requirements...
		self.DJANGO_REQUIREMENTS_FILE="setup/requirements.txt"
		#DJANGO_REQUIREMENTS=[Django, django-bootstrap-toolkit, south, markdown2]

		#### specify any insatlled apps whose db is managed by south
		self.SOUTH_MANAGED_DJANGO_APPS=['printers', 'sparkle']

		WEB_DATA_LOCATION=serveradmin_settings('web','dataLocation')
		if not WEB_DATA_LOCATION:
			WEB_DATA_LOCATION = '/Library/Server/Web/Data/'

		self.OSX_SERVER_WSGI_DIR=os.path.join(WEB_DATA_LOCATION,'WebApps/')
		self.OSX_SERVER_SITES_DEFAULT=os.path.join(WEB_DATA_LOCATION,"/Sites/")
		self.OSX_SERVER_APACHE_DIR="/Library/Server/Web/Config/apache2/"

		self.DJANGO_WEBAPP_VIR_ENV=os.path.join(self.OSX_SERVER_SITES_DEFAULT,
													self.APP_DEFAULT_NAME+'_env')

''' 
These Properties are dynamically generated, and suould normally be acceptable
Howerver in certian situations they may need to be tweaked
'''
	@property
	def APACHE_CONFIG_FILE(self):
		return "httpd_%s.conf" % self.APP_DEFAULT_NAME)
	
	@property
	def VIRENV_NAME(self):
		return "%s_env" % self.APP_DEFAULT_NAME)

	@property
	def WSGI_FILE_NAME(self):
		return "%s.wsgi" % self.APP_DEFAULT_NAME)

	@property
	def USER_NAME(self):
		return self.APP_DEFAULT_NAME)

	@property
	def GROUP_NAME(self):
		return self.APP_DEFAULT_NAME)

	@property
	def DJANGO_WEBAPP_VIR_ENV(self):
		return os.path.join(self.OSX_SERVER_SITES_DEFAULT,self.APP_DEFAULT_NAME+'_env'))
	
	@property
	def PROJECT_SETTINGS_DIR(self):
		return os.path.join(self.DJANGO_WEBAPP_VIR_ENV,
											self.PROJECT_NAME,
											self.PROJECT_SETTINGS_DIR
											))
	@property
	def WSGI_FILE_PATH (self):
		return  os.path.join(self.OSX_SERVER_WSGI_DIR,WSGI_FILE_NAME))


def prompt_for_settings(self):
	self.WSGI_FILE = 'the new value'

# Utility Functions

def install(package=None,file=None):
	if os.path.isfile(file):

def serveradmin_settings(module,value):
	p1 = subprocess.Popen(['/Applications/Server.app/Contents/ServerRoot/usr/sbin/serveradmin','settings','web:dataLocation'],stdout=subprocess.PIPE)
	results = p1.communicate()[0]
	if not p1.returncode == 0:
		return None

	string = results.split('=')[1].strip().strip('\"')
	if string in ('_empty_dictionary',):
		return None
	else:
		return string

def ansii_color_str(message,color=None):
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

def prompt_for_setting():
	cecho("##################################################################",'red')
	cecho("##########         django webapp installer            ############",'red')
	cecho("##################################################################",'red')


def cread(message,color=None):
	str = raw_input(ansii_color_str(message,color));
	if str in ('Y','y','[Yy][Ee][Ss]'):
		return True
	elif str in ('N','n','[Nn][Oo]'):
		return False
	return str

def cecho(message,color=None):
	print(ansii_color_str(message,color));

def writeline(f,line=None):
    if line:
	    f.write(line +'\n')
    else:
    	f.write('\n')

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
    settings = InstallSettings()
    settings.AGAIN = "okdoke"

    print settings.GIT_REPO
    print settings.str(WSGI_FILE_NAME)

    # write_wsgi(WSGI_FILE)



if __name__ == "__main__":
    main()

