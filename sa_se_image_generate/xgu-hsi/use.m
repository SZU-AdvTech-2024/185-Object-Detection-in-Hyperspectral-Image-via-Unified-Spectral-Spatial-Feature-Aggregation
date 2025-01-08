function [Image] = use(file1path)

 
Info=imfinfo(file1path);                                      %%��ȡͼƬ��Ϣ���ж��Ƿ�Ϊtif
tif='tif'; 
format=Info.Format;
if  (strcmp(format ,tif)==0)
    disp('����Ĳ���tifͼ����ȷ�����������');                %%ȷ�������ͼ����tiffͼ��
end
Slice=size(Info,1);                                          %%��ȡͼƬz��֡��
Width=Info.Width;
Height=Info.Height;
Image=zeros(Height,Width,Slice);
for i=1:Slice
    Image(:,:,i)=imread(file1path,i);                         %%һ��һ��Ķ���ͼ��
end

