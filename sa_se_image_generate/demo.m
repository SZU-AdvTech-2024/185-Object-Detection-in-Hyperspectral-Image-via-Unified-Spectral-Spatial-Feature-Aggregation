%% load data

clc , clear;
A = double(importdata('Indian_pines_corrected.mat'));
EEE = ONR(A);

function band_set = ONR(A)
X = permute(A, [3, 1, 2]);
%% normalization
X = X(:, :);
minv = min(X(:)); maxv = max(X(:));

%% run
k = 16; % Number of bands
ONR_L = ONR_init(X');
band_set = ONR(X, ONR_L, k);
end

