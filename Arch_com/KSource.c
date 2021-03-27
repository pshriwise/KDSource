#include<stdlib.h>
#include<stdio.h>
#include<math.h>
#include<string.h>
#include<time.h>

#include "ksource.h"
#include "metrics.h"
#include "plists.h"
#include "aux.h"

#define EPSILON_GEO 1E-4


static int initialized = 0;
static long int N = 0;
static double I = 0, p2 = 0;
static double t_sample = 0;

void source(int *ipt, double *x, double *y, double *z, double *dx, double *dy, double *dz, double *e, double *we, double *param){

	clock_t start = clock();

/************************************************* Input *****************************************************/
	
	#define len 1
	char* filenames[len] = {"/home/inti/Documents/Maestria/Simulaciones/1_guia_n_knn/D_tracks_source.txt"};
	double ws[len] = {1};

	WeightFun bias = NULL; // Funcion de bias

/*********************************************** Fin Input ***************************************************/

   // *********************************** Declaracion variables globales **************************************

	static long int N_simul;

	static MultiSource *msource;
	static double w_crit;

	// **************************************** Inicializacion ************************************************

	int i;
	if(initialized == 0){
		printf("\nCargando fuentes...  ");

		msource = MS_open(len, filenames, ws);
		w_crit = MS_w_mean(msource, 1000);

		N_simul = (param[0]-1)*param[1] + 500 + 1000;

		srand(time(NULL));

		initialized = 1;
		printf("Hecho\n");
	}

	// ********************************************** Sorteo ***********************************************************

	Part part;
	double w;
	char pt;

	MS_sample(msource, &pt, &part, &w, w_crit, bias);

	if(pt == 'n') *ipt = 1;
	else if(pt == 'p') *ipt = 2;
	else{
		printf("Error: Particula no reconocida. Se tomara como neutron.\n");
		*ipt = 1;
	}
	*x = part.pos[0];
	*y = part.pos[1];
	*z = part.pos[2];
	*dx = part.dir[0];
	*dy = part.dir[1];
	*dz = part.dir[2];
	*e = part.E;
	*we = w;

	*x += *dx * EPSILON_GEO;
	*y += *dy * EPSILON_GEO;
	*z += *dz * EPSILON_GEO;

	N++;
	I += *we;
	p2 += *we**we;

	// *********************************************** Finalizacion ***************************************************

	if(N%N_simul == 0){
		printf("\nDestruyendo fuentes...  ");
		
		MS_destroy(msource);

		initialized = 0;
		printf("Hecho\n");
		printf("Tiempo de muestreo: %lf s\n", t_sample);
		printf("Particulas producidas: I err N %lf %lf %ld\n", I, sqrt(p2), N);
	}

	clock_t end = clock();
	t_sample += (float)(end - start) / CLOCKS_PER_SEC;

	return;
}