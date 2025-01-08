clc,clear;

file1path='pad_rgb_0001.tiff';


 [Image] = use(file1path);
% load('Viareggio.mat') % 导入需要显示的影像
% [rgb] = func_hyperImshow(hsi,[219,144,66]); % func_hyperImshow(3D高光谱图像,[R,G,B])
[rgb] = func_hyperImshow(Image,[5,40,90]); % func_hyperImshow(3D高光谱图像,[R,G,B])



