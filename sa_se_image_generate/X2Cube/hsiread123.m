
clc,clear;

Input_path = 'C:\Users\Heed\Desktop\tif\';  
Output_path='C:\Users\Heed\Desktop\tifrgb2\';
namelist = dir(strcat(Input_path,'*.tif'));  %����ļ��������е� .jpgͼƬ
len = length(namelist);
for i = 1:len
    name=namelist(i).name;  %namelist(i).name; %�����õ�ֻ�Ǹ�·���µ��ļ���
    I=imread(strcat(Input_path, name)); %ͼƬ������·����
    
    band_set = ONRAA(I);
    t=I(:,:,[23,48,74]);
    t=imadd(t,0.1);
%     imshow(t);
    
    imwrite(t,[Output_path,'wie',int2str(i),'.jpg']); %������ͼƬ�洢��·����  �������ε����� 
                                          
end



