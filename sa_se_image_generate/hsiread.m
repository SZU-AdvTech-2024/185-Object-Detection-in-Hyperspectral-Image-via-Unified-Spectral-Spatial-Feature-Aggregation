
clc,clear;


% 
% 
% imgPath = 'C:/Users/Heed/Desktop/X2Cube/ir';        % 图像库路径
% 
% imgDir  = dir([imgPath '*.jpg']); % 遍历所有jpg格式文件
% 
% for i = 1:length(imgDir)          % 遍历结构体就可以一一处理图片了
% 
% img = imread([imgPath imgDir(i).name]); %读取每张图片
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