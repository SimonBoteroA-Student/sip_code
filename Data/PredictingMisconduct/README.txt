This readme file explains the contents of the replication folder for:

Predicting Politicians' Misconduct: Evidence from Colombia

Published in Data & Policy. 

Authors:

1. Jorge Gallego, Inter-American Development Bank and Universidad del Rosario. Email: jorge.gallego@urosario.edu.co 
2. Mounu Prem, Einaudi Institute for Economics and Finance
3. Juan F. Vargas, Universidad del Rosario

Main folders:

I. Data. This folder contains all the datasets needed to replicate the paper. All variables have detailed labels. 
1.	MainDatset: final dataset at the county level with all necessary variables for the main analysis.
2.	MainDatset_`J': where J is the group of variables discussed in Table A1. This datasets present all the necessary variable for the group level analysis.

II. Codes. This folder contains the .do files that replicate all tables and figures.
1.	ModelPerformance.R: R code that calibrates the main models shown in the paper.
2.	GroupAnalysis.R:  R code that replicates the group level analysis presented in Figure 2.
3. 	Figure-VariableImportance: dofile that takes the input from GroupAnalysis.R and creates Figure 2.
4. 	Figure-GroupImportance: dofile that takes the input from GroupAnalysis.R and creates the Figure 3.
Note: These do-files contain detailed instructions for their execution. Files in other folders must preserve the folder structure and the path to the main folder must be specified in each do-file.

III. Figures. All figures of the paper in pdf.



