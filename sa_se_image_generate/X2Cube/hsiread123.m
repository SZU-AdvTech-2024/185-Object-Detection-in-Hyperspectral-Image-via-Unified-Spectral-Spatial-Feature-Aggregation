
clc,clear;

Input_path = 'C:\Users\Heed\Desktop\tif\';  
Output_path='C:\Users\Heed\Desktop\tifrgb2\';
namelist = dir(strcat(Input_path,'*.tif'));  %获得文件夹下所有的 .jpg图片
len = length(namelist);
for i = 1:len
    name=namelist(i).name;  %namelist(i).name; %这里获得的只是该路径下的文件名
    I=imread(strcat(Input_path, name)); %图片完整的路径名
    
    band_set = ONRAA(I);
    t=I(:,:,[23,48,74]);
    t=imadd(t,0.1);
%     imshow(t);
    
    imwrite(t,[Output_path,'wie',int2str(i),'.jpg']); %完整的图片存储的路径名  并将整形的数字 
                                          
end



