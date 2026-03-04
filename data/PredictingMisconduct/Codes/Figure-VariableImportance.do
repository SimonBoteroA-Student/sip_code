

clear all 
set more off
cap log close


*********************************************
// Figure 3. Covariates importance
*********************************************

**************
** LASSO
**************
	clear all
	set obs 10
	g id = _n
	g Variable = "Credit for housing" if id == 1
	replace Variable = "Bank offices" if id == 2
	replace Variable = "Index for administration management" if id == 3
	replace Variable = "Development index" if id == 4
	replace Variable = "Medium palm suitability" if id == 5
	replace Variable = "Nighttime lights" if id == 6
	replace Variable = "Distance to military base" if id == 7
	replace Variable = "FARC" if id == 8	
	replace Variable = "Number of candidates" if id == 9
	replace Variable = "Nighttime lights" if id == 10
	
	g Value = 100 if id == 1
	replace Value = 70.76 if id == 2
	replace Value = 67.88 if id == 3
	replace Value = 54.76 if id == 4	
	replace Value = 33.99 if id == 5
	replace Value = 24.69 if id == 6
	replace Value = 22.05 if id == 7
	replace Value = 17.25 if id == 8
	replace Value = 14.98 if id == 9
	replace Value = 12.22 if id == 10
	
	graph hbar Value, over(Variable, sort(id)) ///
			ytitle("")
			
	graph export "VarImp_LASSO.pdf"		, replace
	
**************
** RANDOM FOREST
**************
	clear all
	set obs 10
	g id = _n
	g Variable = "Financial sector workers" if id == 1
	replace Variable = "Development index" if id == 2
	replace Variable = "Index for administration capacity" if id == 3
	replace Variable = "Educational establishments" if id == 4
	replace Variable = "Index for administration capacity" if id == 5
	replace Variable = "Index for fiscal performance" if id == 6
	replace Variable = "Government investments" if id == 7
	replace Variable = "Government transfers" if id == 8
	replace Variable = "Micro credits" if id == 9
	replace Variable = "Nighttime lights" if id == 10
	
	g Value = 100 if id == 1
	replace Value = 77.56 if id == 2
	replace Value = 71.94 if id == 3
	replace Value = 69.99 if id == 4
	replace Value = 69.79 if id == 5
	replace Value = 68.41 if id == 6
	replace Value = 65.28 if id == 7
	replace Value = 64.40 if id == 8
	replace Value = 63.06 if id == 9
	replace Value = 61.53 if id == 10	
	
	
	graph hbar Value, over(Variable, sort(id)) ///
			ytitle("")
			
	graph export "VarImp_RF.pdf"		, replace

	
**************
** GBM
**************
	clear all
	set obs 10
	g id = _n
	g Variable = "Financial sector workers" if id == 1
	replace Variable = "Medium palm suitability" if id == 2
	replace Variable = "Bank offices" if id == 3
	replace Variable = "Government transfers" if id == 4
	replace Variable = "Index for fiscal performance" if id == 5
	replace Variable = "Nighttime lights" if id == 6
	replace Variable = "Development index" if id == 7
	replace Variable = "Index for administration management" if id == 8
	replace Variable = "Educational establishments" if id == 9
	replace Variable = "Infant mortality" if id == 10
	
	g Value = 100 if id == 1
	replace Value = 60.52 if id == 2
	replace Value = 56.07 if id == 3
	replace Value = 43.29 if id == 4
	replace Value = 40.67 if id == 5
	replace Value = 34.13 if id == 6
	replace Value = 31.36 if id == 7
	replace Value = 30.25 if id == 8
	replace Value = 28.23 if id == 9
	replace Value = 25.17 if id == 10
	
	
	graph hbar Value, over(Variable, sort(id)) ///
			ytitle("")
			
	graph export "VarImp_GBM.pdf"		, replace
	
	
**************
** NEURAL NETWORKS
**************
	clear all
	set obs 10
	g id = _n
	g Variable = "Development index" if id == 1
	replace Variable = "Nighttime lights" if id == 2
	replace Variable = "Homicide rate" if id == 3
	replace Variable = "Bank offices" if id == 4
	replace Variable = "Any FARC event" if id == 5
	replace Variable = "Medium palm suitability" if id == 6
	replace Variable = "Education sector workers" if id == 7
	replace Variable = "FARC attacks" if id == 8
	replace Variable = "Government total revenue" if id == 9
	replace Variable = "Number of secondary students" if id == 10
	
	g Value = 100 if id == 1
	replace Value = 90.88 if id == 2
	replace Value = 82.59 if id == 3
	replace Value = 81.83 if id == 4
	replace Value = 75.26 if id == 5
	replace Value = 72.56 if id == 6
	replace Value = 71.23 if id == 7
	replace Value = 68.67 if id == 8
	replace Value = 65.34 if id == 9
	replace Value = 58.58 if id == 10
	
	graph hbar Value, over(Variable, sort(id)) ///
			ytitle("")
			
	graph export "VarImp_NN.pdf"		, replace
		
		

				
