#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Module for reading tallies from MC simulations
"""

import os

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as col
from PIL import Image as Im

from .plist import convert2mcpl,savessv,appendssv


def read_spectrum(spectrum=None):
    """
    Read and load decay spectrum from CSV file.

    Decay spectrum files can be downloaded from:
        https://www-nds.iaea.org/relnsd/vcharthtml/VChartHTML.html
    Select nuclide, and in 'Decay Radiation' tab download Gamma table as
    CSV.

    Parameters
    ----------
    spectrum: str
        Name of CSV file with decay spectrum. Energy and intensity
        values must be in first and third column, respectively. If None,
        empty spectrum is returned.

    Returns
    -------
    [Es, ws]: list
        Energy and intensity values.
    """
    Es = []
    ws = []
    if spectrum is not None:
        with open(spectrum, "r") as file:
            for line in file:
                try:
                    line = line.split(sep=',')
                    Es.append(np.double(line[0])/1000.)
                    ws.append(np.double(line[2]))
                except:
                    pass  
        if len(Es) == 0:
            raise Exception("Empty decay spectrum.")
    Es = np.array(Es)
    ws = np.array(ws)
    if len(Es) != len(ws):
        raise Exception("Invalid decay spectrum format.")
    return [Es, ws]

class T4Tally:
    varnames = ["x","y","z"]
    varmap = {name:idx for idx,name in enumerate(varnames)}
    units = ["cm","cm","cm"]

    def __init__(self, outputfile, tallyname, spectrum=None, geomplot=None, J=1.0):
        """
        Object for reading TRIPOLI-4 3D tallies.

        Tally must have mesh of type EXTENDED_MESH, and FRAME CARTESIAN.

        This object has two main uses:
            - Reading activation tallies and converting them to gamma
              lists, which can then be used to generate KSource object.
            - Reading and plotting dose maps.

        Parameters
        ----------
        outputfile: str
            Name of output file generated by TRIPOLI-4.
        talyname: str
            Name of the tally to read.
        spectrum: str, optional
            Name of file with decay spectrum. Needed only for converting
            activation tally to gamma list.
        geomplot: str, optional
            Name of file with geometry graph, to add contour lines to
            plot. This file must be generated with GRAPH command, on the
            same region than the tally.
        J: float, optional
            Intensity of the source of the TRIPOLI-4 simulation, in
            [1/s].
        """
        self.J = J
        self.folder = os.path.dirname(outputfile)
        self.outputfile = outputfile
        self.tallyname = tallyname
        # Read decay spectrum
        self.Es,self.Ews = read_spectrum(spectrum)
        # Read geometry graph
        if geomplot is not None:
            geomplot = np.array(Im.open(geomplot).convert('L').crop((25,26,514,514)))
        self.geomplot = geomplot
        # Read tallies
        with open(outputfile, "r") as file:
            # Search SCORE block
            for line in file:
                if "SCORE" in line:
                    break
            else:
                raise Exception("No SCORE block in outputfile.")
            # Search tally definition
            for line in file:
                if tallyname+" " in line or tallyname+"\t" in line or tallyname+"\n" in line:
                    break
                if "END_SCORE" in line:
                    raise Exception("Tally {} definition not found.".format(tallyname))
            # Search mesh
            for line in file:
                if "EXTENDED_MESH" in line:
                    break
                if "NAME" in line or "END_SCORE" in line:
                    raise Exception("EXTENDED_MESH not found.")
            # Read mesh parameters
            buf = []
            idx = line.split().index("EXTENDED_MESH")
            buf.extend(line.split()[idx+1:]) # Accumulate data after EXTENDED_MESH
            for line in file:
                if "FRAME" in line:
                    break
                buf.extend(line.split())
            idx = line.split().index("FRAME")
            buf.extend(line.split()[:idx]) # Accumulate data before FRAME
            if len(buf) != 10:
                raise Exception("Could not read EXTENDED_MESH.")
            mins = np.double(buf[1:4])
            maxs = np.double(buf[4:7])
            Ns = list(map(int, buf[7:10]))
            grid1 = np.linspace(mins[0], maxs[0], Ns[0]+1)
            grid2 = np.linspace(mins[1], maxs[1], Ns[1]+1)
            grid3 = np.linspace(mins[2], maxs[2], Ns[2]+1)
            self.grids = [grid1, grid2, grid3]
            self.vcell = np.abs((grid1[1]-grid1[0])*(grid2[1]-grid2[0])*(grid3[1]-grid3[0]))
            # Read coordinates
            if not "FRAME CARTESIAN" in line:
                raise Exception("Tally must have FRAME CARTESIAN.")
            buf = []
            idx = line.split().index("CARTESIAN")
            buf.extend(line.split()[idx+1:]) # Accumulate data after CARTESIAN
            for line in file:
                found = False
                for search in ["NAME", "END_SCORE", "//", "/*"]:
                    if search in line:
                        if not found:
                            idx = line.split().index(search)
                            found = True
                        else:
                            idx2 = line.split().index(search)
                            if idx2 < idx: idx = idx2
                if found: break
                buf.extend(line.split())
            buf.extend(line.split()[:idx]) # Accumulate data before NAME or END_SCORE
            if len(buf) != 12:
                raise Exception("Could not read FRAME CARTESIAN.")
            self.origin = np.double(buf[:3])
            self.dx1 = np.double(buf[3:6])
            self.dx2 = np.double(buf[6:9])
            self.dx3 = np.double(buf[9:12])
            # Search tally results
            I = []
            err = []
            for line in file:
                if "SCORE NAME : "+tallyname in line:
                    break
            else:
                raise Exception("Tally {} results not found.".format(tallyname))
            for line in file:
                if "Energy range" in line:
                    break
            for line in file:
                line = line.split()
                if len(line) == 0:
                    break
                I.append(np.double(line[1]))
                err.append(np.double(line[2]))
        if len(I) == np.prod(Ns):
            print("Tally {} successfully read.".format(tallyname))
        else:
            print("Tally {} reading incomplete.".format(tallyname))
        self.I = np.reshape(I, Ns) / self.vcell
        self.err = np.reshape(err, Ns) / self.vcell

    def save_tracks(self, filename=None):
        """
        Save activation tally as gamma list.

        For each tally cell, one gamma per decay energy is generated in
        its center, with random direction. Each gamma weight is the
        product of the cell tally value and the intensity of the energy
        value, normalized to have mean weight of 1 (or close).

        Parameters
        ----------
        filename: str
            Name of the particle list to generate. Will have MCPL
            format, but the .mcpl suffix is not needed.

        Returns
        -------
        trackfile: str, optional
            Name of generated MCPL file. By default the tally name is
            used.
        """
        if(len(self.Es) == 0):
            raise Exception("No decay spectrum.")
        pt = "p"
        if filename is None:
            filename = self.folder + "/" + self.tallyname + ".ssv"
        # Create position list
        grids = [(grid[:-1]+grid[1:])/2 for grid in self.grids]
        poss = np.reshape(np.meshgrid(*grids, indexing='ij'),(3,-1)).T
        pos_ws = self.I.reshape(-1)
        poss = poss[pos_ws>0]
        pos_ws = pos_ws[pos_ws>0]
        pos_ws /= pos_ws.mean()
        N = len(poss)
        # Create particle list
        parts = np.zeros((N, 7))
        parts[:,1:4] = poss
        np.random.shuffle(parts)
        # Create energy list (cyclic)
        nloops = int(np.ceil(N/len(self.Es)) + 1)
        Es = np.tile(self.Es,nloops)
        E_ws = np.tile(self.E_ws,nloops)
        E_ws /= E_ws.mean()
        # Save in file
        savessv(pt, [], [], filename) # Create header
        for i in range(len(self.Es)):
            parts[:,0] = Es[i:i+N] # Energies
            mus = -1 + 2*np.random.rand(N)
            dxys = np.sqrt(1-mus**2)
            phis = -np.pi + 2*np.pi*np.random.rand(N)
            dirs = np.array([dxys*np.cos(phis), dxys*np.sin(phis), mus]).T
            parts[:,4:7] = dirs # Random directions
            ws = pos_ws*E_ws[i:i+N] # Weights
            appendssv(pt, parts, ws, filename)
        mcplname = convert2mcpl(filename, "ssv")
        print("Particle list successfully saved in {}.".format(mcplname))
        return mcplname

    def plot(self, var, cells=None, **kwargs):
        """
        1D plot of tally.

        Parameters
        ----------
        var: str or int
            Variable to be plotted, or its index. Names and indices of
            variables can be found in cls.varnames.
        cells: list or None
            Indices of fixed cells for other variables. If None, tally
            is averaged over other variables.
        **kwargs: optional
            Additional parameters for plotting options:
            xscale: 'linear' or 'log'
                Scale for x axis. Default: 'linear'
            yscale: 'linear' or 'log'. Default: 'log'
                Scale for y axis.
            fact: float
                Factor to apply on all densities. Default: 1
            label: string
                Label for plot legend.

        Returns
        -------
        [fig, [scores, errs]]:
            Figure object, and plotted tally values and statistic
            errors.
        """
        if isinstance(var, str):
            var = self.varmap[var]
        if not "xscale" in kwargs: kwargs["xscale"] = "linear"
        if not "yscale" in kwargs: kwargs["yscale"] = "log"
        vrs = [0,1,2]
        vrs.remove(var)
        if cells is None: # Average over other variables
            scores = np.mean(self.I, axis=tuple(vrs))
            errs = np.sqrt(np.sum(self.err**2, axis=tuple(vrs))) / (self.err.shape[vrs[0]]*self.err.shape[vrs[1]])
        else: # Plot over selected cells
            slc = cells.copy()
            slc.insert(var, slice(None))
            scores = self.I[tuple(slc)]
            errs = self.err[tuple(slc)]
        scores *= self.J
        errs *= self.J
        if np.sum(scores) == 0:
            print("Null tally in plot region.")
            return [None, [scores,errs]]
        if "fact" in kwargs:
            scores *= kwargs["fact"]
            errs *= kwargs["fact"]
        #
        if "label" in kwargs: lbl = kwargs["label"]
        else:
            if cells is None:
                lbl = str(self.grids[vrs[0]][0])+" <= "+self.varnames[vrs[0]]+" <= "+str(self.grids[vrs[0]][-1])
                lbl += str(self.grids[vrs[1]][0])+" <= "+self.varnames[vrs[1]]+" <= "+str(self.grids[vrs[1]][-1])
            else:
                lbl = str(self.grids[vrs[0]][cells[0]])+" <= "+self.varnames[vrs[0]]+" <= "+str(self.grids[vrs[0]][cells[0]+1])
                lbl += str(self.grids[vrs[1]][cells[1]])+" <= "+self.varnames[vrs[1]]+" <= "+str(self.grids[vrs[1]][cells[1]+1])
        grid = (self.grids[var][:-1] + self.grids[var][1:]) / 2
        plt.errorbar(grid, scores, errs, fmt='-s', label=lbl)
        plt.xscale(kwargs["xscale"])
        plt.yscale(kwargs["yscale"])
        plt.xlabel(r"${}\ [{}]$".format(self.varnames[var], self.units[var]))
        plt.ylabel("Tally")
        plt.grid()
        plt.legend()
        return [plt.gcf(), [scores,errs]]

    def plot2D(self, vrs, cell=None, geomplot=False, levelcurves=None, **kwargs):
        """
        2D plot of tally.

        Parameters
        ----------
        vrs: list
            Variables to be plotted, or its indices. Names and indices
            of variables can be found in cls.varnames.
        cell: int or None
            Index of fixed cell for other variable. If None, tally is
            averaged over other variable.
        geomplot: bool
            Whether to plot geometry contours.
        levelcurves: list or None
            If a list, gives the tally values to plot level curves.
        **kwargs: optional
            Additional parameters for plotting options:
            scale: 'linear' or 'log'
                Scale for color map. Default: 'log'
            fact: float
                Factor to apply on all densities. Default: 1

        Returns
        -------
        [fig, [scores, errs]]:
            Figure object, and plotted tally values and statistic
            errors.
        """
        if isinstance(vrs[0], str):
            vrs = [self.varmap[var] for var in vrs]
        if not "scale" in kwargs: kwargs["scale"] = "log"
        var = [0,1,2]
        var.remove(vrs[0])
        var.remove(vrs[1])
        var = var[0]
        if cell is None: # Average var variable
            scores = np.mean(self.I, axis=var)
            errs = np.sqrt(np.sum(self.err**2, axis=var)) / self.err.shape[var]
        else: # Plot over selected cell
            slc = 2 * [slice(None)]
            slc.insert(var, cell)
            scores = self.I[tuple(slc)]
            errs = self.err[tuple(slc)]
        scores *= self.J
        errs *= self.J
        if np.sum(scores) == 0:
            print("Null tally in plot region.")
            return [None, [scores,errs]]
        if "fact" in kwargs:
            scores *= kwargs["fact"]
            errs *= kwargs["fact"]
        if vrs[0] > vrs[1]:
            scores = np.transpose(scores)
            errs = np.transpose(errs)
        scores = np.rot90(scores)
        errs = np.rot90(errs)
        #
        if kwargs["scale"] == "log": norm = col.LogNorm()
        else: norm = None
        extent = (self.grids[vrs[0]][0], self.grids[vrs[0]][-1], self.grids[vrs[1]][0], self.grids[vrs[1]][-1])
        plt.imshow(scores, extent=extent, cmap="jet", norm=norm, aspect='auto')
        plt.colorbar()
        title = "Tally"
        if cell is None:
            title += "\n"+str(self.grids[var][0])+" <= "+self.varnames[var]+" <= "+str(self.grids[var][-1])
        else:
            title += "\n"+str(self.grids[var][cell])+" <= "+self.varnames[var]+" <= "+str(self.grids[var][cell+1])
        plt.title(title)
        plt.xlabel(r"${}\ [{}]$".format(self.varnames[vrs[0]], self.units[vrs[0]]))
        plt.ylabel(r"${}\ [{}]$".format(self.varnames[vrs[1]], self.units[vrs[1]]))
        plt.tight_layout()
        #
        if levelcurves is not None:
            plt.contour(scores, levelcurves, extent=extent, linewidths=0.5)
        #
        if self.geomplot is not None and geomplot:
            ext = (extent[0], extent[1], extent[3], extent[2])
            for val in np.unique(self.geomplot):
                plt.contour(self.geomplot==val, [0.5], colors='black', extent=ext, linewidths=0.25)
        #
        return [plt.gcf(), [scores,errs]]