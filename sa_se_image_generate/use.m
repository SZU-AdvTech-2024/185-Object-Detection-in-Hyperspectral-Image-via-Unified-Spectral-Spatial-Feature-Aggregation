function [Image] = use(file1path)

 
Info=imfinfo(file1path);                                      %%获取图片信息并判断是否为tif
tif='tif'; 
format=Info.Format;
if  (strcmp(format ,tif)==0)
    disp('载入的不是tif图像，请确认载入的数据');                %%确保载入的图像是tiff图像
end
Slice=size(Info,1);                                          %%获取图片z向帧数
Width=Info.Width;
Height=Info.Height;
Image=zeros(Height,Width,Slice);
for i=1:Slice
    Image(:,:,i)=imread(file1path,i);                         %%一层一层的读入图像
end

