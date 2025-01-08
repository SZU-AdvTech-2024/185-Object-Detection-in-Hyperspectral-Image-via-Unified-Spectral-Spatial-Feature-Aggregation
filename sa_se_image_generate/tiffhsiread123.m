
clc,clear;

Input_path = 'E:\Optimal-Neighboring-Reconstruction-for-Hyperspectral-Band-Selection-master\�߹������ݼ�ԭʼ\test\';  
Output_path='E:\Optimal-Neighboring-Reconstruction-for-Hyperspectral-Band-Selection-master\hsimebandselect\test\';
Output_path2='E:\Optimal-Neighboring-Reconstruction-for-Hyperspectral-Band-Selection-master\hsimebandselect\test-1\';
namelist = dir(strcat(Input_path,'*.png'));  %����ļ��������е� .jpgͼƬ
len = length(namelist);

for i = 1:len

    name=namelist(i).name;  %namelist(i).name; %�����õ�ֻ�Ǹ�·���µ��ļ���
%     I=imread(strcat(Input_path, name)); %ͼƬ������·����
     [Image] = imread(strcat(Input_path, name));
     
        Image=X2Cube(Image);
%      [Image] = use(strcat(Input_path, name));
        valband=band_set_number(Image);
%     rgb=PCAT(Image);
val=valband(1:2:end);
val2=valband(2:2:end);
rgb1=Image(:,:,val);
rgb2=Image(:,:,val2);
%  rgb1=PCAT(Image);
%  rgb2=PCAT(val2);
%   [rgb1] = func_hyperImshow(Image,val); % func_hyperImshow(3D�߹���ͼ��,[R,G,B])
%   [rgb2] = func_hyperImshow(Image,val2); % func_hyperImshow(3D�߹���ͼ��,[R,G,B])

%     imshow(rgb1);
% name=name(1:end-5);
    imwrite(rgb1,[Output_path,name,'.jpg']); %������ͼƬ�洢��·����  �������ε����� 
    imwrite(rgb2,[Output_path2,name,'.jpg']); %������ͼƬ�洢��·����  �������ε����� 
                                                          
end

B=DataCube(:,:,3);
Bmax=max(max(B));
Bmin=min(min(B));
B=(B-Bmin)/(Bmax-Bmin);
imagesc(B);

%  imshow(t(:,:,1));

function ans=band_set_number(A)
X = permute(A, [3, 1, 2]);

% Here X can be linearly normalized to [0, 1], or just keep unchanged.
X = X(:, :);


% Number of bands
k = 6;

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

sort(band_set)

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

sort(band_set)

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

sort(band_set)
end


function RES=PCAT(a)
[m,n,p]=size(a);%(610,340,103)
t=m*n;%207400
a=reshape(a,t,p);%(207400,103),��(��������������)
[pc,score,latent,tsquare]=pca(a);%pcΪ���ɷ�ϵ����scoreΪ���ɷֵĽ����latentΪ����
feature_after_PCA=score(:,1:3);
RES=reshape(feature_after_PCA,m,n,3);
% imshow(RES(:,:,2))
end
