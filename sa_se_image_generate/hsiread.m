
clc,clear;


% 
% 
% imgPath = 'C:/Users/Heed/Desktop/X2Cube/ir';        % ͼ���·��
% 
% imgDir  = dir([imgPath '*.jpg']); % ��������jpg��ʽ�ļ�
% 
% for i = 1:length(imgDir)          % �����ṹ��Ϳ���һһ����ͼƬ��
% 
% img = imread([imgPath imgDir(i).name]); %��ȡÿ��ͼƬ
% 
% end


i = imread('0004.png');
DataCube=X2Cube(i);
a=DataCube;

t=a(:,:,4);
t=t*10/255;
imshow(t)

% clc,clear;
% H1=imread('rgb/00001.jpg');
% 
% 
% core = fspecial('gaussian',[5,5],1);
% C = filter2(core,H1);
% imshow(C)