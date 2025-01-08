
clc,clear;

Input_path = 'E:\Optimal-Neighboring-Reconstruction-for-Hyperspectral-Band-Selection-master\�߹������ݼ�ԭʼ\train\';  
Output_path='E:\Optimal-Neighboring-Reconstruction-for-Hyperspectral-Band-Selection-master\hsimebandselect\train\';
Output_path2='E:\Optimal-Neighboring-Reconstruction-for-Hyperspectral-Band-Selection-master\hsimebandselect\train-1\';
namelist = dir(strcat(Input_path,'*.png'));  %����ļ��������е� .jpgͼƬ
len = length(namelist);
for i = 1:2

    name=namelist(i).name;  %namelist(i).name; %�����õ�ֻ�Ǹ�·���µ��ļ���
    I=imread(strcat(Input_path, name)); %ͼƬ������·����
    
    DataCube=X2Cube(I);


 ans=band_set_number(DataCube);
    t=DataCube(:,:,1);
    imagesc(t);

    imwrite(t,[Output_path,name,'']); %������ͼƬ�洢��·����  �������ε����� 
    imwrite(t,[Output_path2,name,'']); %������ͼƬ�洢��·����  �������ε�����        
    
    
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
