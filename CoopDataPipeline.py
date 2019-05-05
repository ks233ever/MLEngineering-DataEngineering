import paramiko
import datetime
import civis
import sys
import os
import boto3
import pandas as pd
import numpy as np
from zipfile import ZipFile

from civis.io import query_civis
client = civis.APIClient()
from list_utils.civis_jobs import CivisJobs
import seaborn as sns
import matplotlib.pyplot as plt
from list_utils.query_to_pandas import QuerytoDataFrame


class ProcessCoop:

    def __init__(self, mailing, path):
        self.mailing = mailing
        self.path = path
        self.df_final = None
      	#below attributes get passed into civis jobs
        self.schema = 'external_lists'
        self.rawtable = ""
        self.intermedtable = ""

    #download files from an FTP site
    def ftp_download(self):

        os.mkdir(self.path + '/{}'.format(self.mailing))

        transport = paramiko.Transport(('XXXXXXXX', 22))
        transport.connect(username='XXXXX', password='XXXXX')
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.chdir(path='XXXXXXX/Out/')

        # download the zip files from the FTP into the proper mailing folder
        downloads = []
        for filename in sorted(sftp.listdir()):
            sftp.get(filename, self.path + '/{}/{}.zip'.format(self.mailing, filename))
            downloads.append(filename)

        sftp.close()

        print('Downloaded the following files into your path: {}'.format(downloads))

    #Upload files to an S3 bucket
    def s3_upload(self):
    	session = boto3.Session()
    	# low-level client interfact
        s3_client = session.client('s3')
		# high level interface
        s3_resource = session.resource('s3')

        bucket = s3_resource.Bucket('XXXXXX')
        print('The current directories in your S3 bucket are: ')
        for obj in bucket.objects.all():
            print(obj.key)

        print('\n')

        rootdir = self.path + '/{}/'.format(self.mailing)

  		# creating a list of zip file paths to extract
        coop_paths = []
        for subdir, dirs, files in os.walk(rootdir):
            print('Grabbing the downloaded zip file paths to extract: ')
            for file in files:
                if '.csv' not in file:
                    w_path = os.path.join(subdir, file)
                    print(w_path)
                    coop_paths.append(w_path)

        print('total coop files to extract: ', len(coop_paths))
        print('\n')

		# creating a list of extracted file names that we will upload to s3
        s3_files = []
        for i in coop_paths:

    		# Create a ZipFile Object
            with ZipFile(i, 'r') as zipObj:
       			# Get a list of all archived file names from the zip
                listOfFileNames = zipObj.namelist()
       			# Iterate over the file names
                for fileName in listOfFileNames:
           	 		# Check filename doesn't have layout in it
                    if 'layout' not in fileName:
               			# Extract the single file from zip to upload to s3
                        zipObj.extract(fileName, self.path + '/{}/Unzipped'.format(self.mailing))
                        s3_files.append(fileName)

        print('We have {} extracted files to upload to the S3 bucket:'.format(len(s3_files)))
        print(s3_files)
        print('\n')

        for f in s3_files:
            filepath = self.path + '/{}/Unzipped/'.format(self.mailing) + f
            s3_resource.Bucket('XXXXXX').upload_file(
            Filename=filepath, Key='coop/coop/{}/{}'.format(self.mailing, f))

        bucket = s3_resource.Bucket('XXXXXX')
        print('Files in the S3 bucket now include: ')
        for obj in bucket.objects.all():
            print(obj.key)
        print('\n')

    #download files from the S3 bucket
    def s3_download(self):
        session = boto3.Session()
    	# low-level client interfact
        s3_client = session.client('s3')
		  # high level interface
        s3_resource = session.resource('s3')

        bucket = s3_resource.Bucket('XXXXXX')

        recent_coop_files = []
        print('The following {} coop files will be downloaded into an S3_downloads folder within your path: '.format(self.mailing))
        for obj in bucket.objects.filter(Prefix='coop/coop/{}'.format(self.mailing)):  
            recent_coop_files.append(obj.key)
            print(obj.key)
        print('\n')

    	# creating the new directory to download into
        os.mkdir(self.path + '/{}/S3_downloads'.format(self.mailing))

        for f in recent_coop_files:
            filename = ''.join(f.split('/')[-1:])
            s3_resource.Bucket('cce-partnerlists').download_file(f, self.path + '/{}/S3_downloads/{}'.format(self.mailing, filename))
        print('Download complete!')

    # process the files for Amazon Redshift import
    def redshift_preprocess(self):

        rootdir = self.path + '/{}/S3_downloads'.format(self.mailing)
        

        coop_paths = []
        print('Processing the following coop files: ')

        for subdir, dirs, files in os.walk(rootdir):
            for file in files:
            	wpath = os.path.join(subdir, file)
            	print(wpath)
            	coop_paths.append(wpath)

		print('total coop files to process: {}'.format(len(coop_paths)))

        fwidth = [25,15,40,15,40,15,15,40,40,40,28,2,6,4,2,2,10,60,1]
        cols_to_use = [0,1,2,3,4,5,8,9,10,11,12,13,14,15,16]
        col_names = ['X','X','X', 'X','X',
            'X','X','X','X','X','X',
            'X','X','X','X']


        coop_dfs = []

        for i, w_path in enumerate(coop_paths):
            df = pd.read_fwf(w_path, widths=fwidth, header=None, dtype=str, usecols=cols_to_use)
            df.columns = col_names
            coop_dfs.append(df)
        df_final = pd.concat(coop_dfs)
		# replace nulls
        df_final = df_final.replace('nan', np.nan)
        df_final = df_final.replace('NaN', np.nan)
        df_final = df_final.dropna(subset=['X', 'X', 'X'])
		
        df_final = df_final.reset_index(drop=True)
        df_final['listid'] = 'X' + df_final.index.astype(str)
		
        assert df_final['listid'].nunique() == df_final.shape[0]

        df_final['fullname'] = df_final['firstname'] + ' ' + df_final['lastname']
	
        df_final['list'] = 'coop: ' + df_final['keycode']
        print('\n')
        print(df_final.shape)
        print(df_final.info())
        print('\n')
        print('Check out this sample and make sure it looks good to import to Redshift!')
        self.df_final = df_final
        return df_final.sample(20)

    
    # upload processed data to Redshift
    def redshift_upload(self):

		client = civis.APIClient()
		client.databases.list()
		DATABASE = "Ethical Electric"

		import_fut = civis.io.dataframe_to_civis(df = self.df_final,
                                        database = 'Ethical Electric',
                                        table = 'external_lists.{}_XXXXX'.format(self.mailing),
                                        existing_table_rows = 'drop',
                                        headers = True,
                                        hidden = False)
		self.rawtable = '{}_coop_XXXXX'.format(self.mailing)
		self.intermedtable= '{}_coop_XXXXX'.format(self.mailing)
		
		print import_fut.result()
		print('\n')
		print('coop import complete! The table location is external_lists.{}_XXXXX'.format(self.mailing))

