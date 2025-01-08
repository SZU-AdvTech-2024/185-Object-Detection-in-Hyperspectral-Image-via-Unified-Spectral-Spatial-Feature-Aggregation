
clc,clear;




imgPath = 'E:/X2Cube/123/';        % 图像库路径
imgsavePath = 'E:/X2Cube/1234/';    
imgDir  = dir([imgPath '*.tif']); % 遍历所有jpg格式文件
t=0;

% length(imgDir)  
for i = 1:length(imgDir)           % 遍历结构体就可以一一处理图片了
t=t+1;
img = imread([imgPath imgDir(i).name]); %读取每张图片
DataCube=img;
% DataCube = X2Cube(img);
% band_set = onr11(DataCube);
% PCAData = DataCube(:,:,band_set);
 PCAData=PCAT(DataCube);

% AAAA = permute(PCAData, [3, 1, 2]);
% AAA=AAAA(:,:);
% A1=mapminmax(AAA,0,255);
% 
% A2=reshape(A1,3,256,438);
% AAAA = permute(A2, [ 2, 3,1]);


rrr=[imgsavePath,imgDir(i).name];

imwrite(PCAData, rrr);

end


% i = imread('image/0001.png');
% DataCube=X2Cube(i);
% a=DataCube;


function RES=PCAT(a)
[m,n,p]=size(a);%(610,340,103)
t=m*n;%207400
a=reshape(a,t,p);%(207400,103),即(样本数，波段数)
[pc,score,latent,tsquare]=pca(a);%pc为主成分系数，score为主成分的结果，latent为方差
feature_after_PCA=score(:,1:3);
RES=reshape(feature_after_PCA,m,n,3);
% imshow(RES(:,:,2))
end

function band_set = ONRAA(A)
X = permute(A, [3, 1, 2]);
%% normalization
X = X(:, :);
minv = min(X(:)); maxv = max(X(:));
X = (X - minv) / (maxv - minv);
%% run
k = 9; % Number of bands
ONR_L = ONR_init(X');
band_set = ONR(X, ONR_L, k);
end




function band_set = onr11(A)

X = permute(A, [3, 1, 2]);

% Here X can be linearly normalized to [0, 1], or just keep unchanged.
X = X(:, :);


% Number of bands
k = 3;

%% An example to conduct TRC-OC-FDPC:

% Achieve the ranking values of band via E-FDPC algorithm
[L, ~] = size(X);
D = E_FDPC_get_D(X');
[~, bnds_rnk_FDPC] = E_FDPC(D, L);

% Construct a similarity graph
S_FG = get_graph(X);

% Get the map f in Eq. (16)
F_TRC_FDPC = get_F_TRC(S_FG, bnds_rnk_FDPC);

% Set the parameters of OCF, to indicate the objective function is TRC
para_TRC_FDPC.bnds_rnk = bnds_rnk_FDPC;
para_TRC_FDPC.F = F_TRC_FDPC;
para_TRC_FDPC.is_maximize = 0; % TRC should be minimized
para_TRC_FDPC.X = X; 
para_TRC_FDPC.operator_name = 'max'; % use 'max' operator for Eq. (8)

% Selection
band_set = ocf(para_TRC_FDPC, k);

sort(band_set);

%% An example to conduct NC-OC-MVPCA:

% Achieve the ranking values of band via MVPCA algorithm
[para_NC_PCA.bnds_rnk, ~ ] = MVPCA(X);

% Construct a similarity graph
S_FG = get_graph(X);

% Get the map f in Eq. (16)
F_NC_FG = get_F_NC(S_FG);

% Set the parameters of OCF, to indicate the objective function is NC
para_NC_PCA.F = F_NC_FG;
para_NC_PCA.is_maximize = 1; % NC should be maximized
para_NC_PCA.X = X; 
para_NC_PCA.operator_name = 'sum'; % use 'sum' operator for Eq. (8)

% Selection
band_set = ocf(para_NC_PCA, k);

sort(band_set);

%% An example to conduct NC-OC-IE:

% Achieve the ranking values of band via MVPCA algorithm
[para_NC_IE.bnds_rnk, ~] = Entrop(X);

% Construct a similarity graph
S_FG = get_graph(X);

% Set the parameters of OCF, to indicate the objective function is NC
para_NC_IE.F = F_NC_FG; 
para_NC_IE.is_maximize = 1; % NC should be maximized
para_NC_IE.X = X; 
para_NC_IE.operator_name = 'sum'; % use 'sum' operator for Eq. (8)

% Selection
band_set = ocf(para_NC_IE, k);

sort(band_set);
end
