/**
 * CAD model loader for the robot camera visualizer.
 *
 * Loads GLTF/GLB models, provides transparency control,
 * click-to-select with bounding box and transform output.
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

const INCHES_PER_METER = 1 / 0.0254;

export class CadModelManager {
  constructor(scene) {
    this.scene = scene;
    this.model = null;            // THREE.Group — loaded GLTF scene root
    this.meshes = [];             // [{ mesh, originalColor }]
    this.opacity = 0.5;
    this.selectedMesh = null;
    this.selectionBox = null;     // THREE.BoxHelper
    this.showBBox = true;
    this.onSelect = null;         // callback(info) where info = { name, center, size, point }
    this.onStatusChange = null;   // callback(statusText)
    this._loader = new GLTFLoader();
    // Draco decoder for compressed GLTF (e.g. Onshape exports)
    const dracoLoader = new DRACOLoader();
    dracoLoader.setDecoderPath(
      'https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/'
    );
    this._loader.setDRACOLoader(dracoLoader);
    this._appliedScale = 1.0;
  }

  // ── Loading ──────────────────────────────────────────────────────

  async loadUrl(url) {
    const name = url.split('/').pop();
    this._setStatus(`Loading ${name}...`);
    return new Promise((resolve, reject) => {
      this._loader.load(
        url,
        (gltf) => {
          this._setStatus(`Processing ${name}...`);
          // Defer to let the status update render
          setTimeout(() => {
            this._onGltfLoaded(gltf);
            resolve();
          }, 50);
        },
        (progress) => {
          if (progress.total > 0) {
            const pct = Math.round((progress.loaded / progress.total) * 100);
            this._setStatus(`Loading ${name}... ${pct}%`);
          } else {
            const mb = (progress.loaded / 1024 / 1024).toFixed(1);
            this._setStatus(`Loading ${name}... ${mb} MB`);
          }
        },
        (err) => {
          this._setStatus(`Error: ${err.message || err}`);
          reject(err);
        },
      );
    });
  }

  async loadFile(file) {
    this._setStatus(`Loading ${file.name}...`);
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = async (e) => {
        try {
          const gltf = await this._loader.parseAsync(
            e.target.result, ''
          );
          this._onGltfLoaded(gltf);
          resolve();
        } catch (err) {
          this._setStatus(`Error: ${err.message}`);
          reject(err);
        }
      };
      reader.onerror = () => {
        this._setStatus('Error reading file');
        reject(reader.error);
      };
      reader.readAsArrayBuffer(file);
    });
  }

  _onGltfLoaded(gltf) {
    this.unload();

    const root = gltf.scene;

    // Measure raw bounding box before any transforms
    const rawBox = new THREE.Box3().setFromObject(root);
    const rawSize = rawBox.getSize(new THREE.Vector3());
    const rawCenter = rawBox.getCenter(new THREE.Vector3());
    const maxDim = Math.max(rawSize.x, rawSize.y, rawSize.z);
    console.log(`[CAD] Raw bounding box: size=(${rawSize.x.toFixed(3)}, ${rawSize.y.toFixed(3)}, ${rawSize.z.toFixed(3)}) center=(${rawCenter.x.toFixed(3)}, ${rawCenter.y.toFixed(3)}, ${rawCenter.z.toFixed(3)}) maxDim=${maxDim.toFixed(3)}`);

    // Auto-detect units based on size
    // A typical FRC robot is ~0.6-1.0m. With bumpers/mechanisms up to ~2m.
    // If maxDim > 20, likely inches (24" = 0.6m robot reads as 24).
    // If maxDim > 200, likely millimeters (600mm = 0.6m robot reads as 600).
    let unitNote = 'meters';
    if (maxDim > 200) {
      this._appliedScale = 0.001;
      root.scale.set(0.001, 0.001, 0.001);
      unitNote = 'mm→meters';
    } else if (maxDim > 20) {
      this._appliedScale = 0.0254;
      root.scale.set(0.0254, 0.0254, 0.0254);
      unitNote = 'inches→meters';
    } else {
      this._appliedScale = 1.0;
    }

    // X rotation to convert coordinate systems, adjustable with Flip button.
    // 0=none, 1=+90°, 2=180°, 3=-90° around X
    this._xSteps = 1;  // 90° X — correct for Onshape GLTF exports
    this._yawSteps = 2; // 180° yaw — Onshape exports are rear-facing by default
    this.model = root;  // set before _applyOrientation so it doesn't bail
    this._applyOrientation();
    this.scene.add(root);

    // Log final bounding box for debugging
    root.updateMatrixWorld(true);
    const finalBox = new THREE.Box3().setFromObject(root);
    const finalSize = finalBox.getSize(new THREE.Vector3());
    const finalCenter = finalBox.getCenter(new THREE.Vector3());
    console.log(`[CAD] Final bounding box: size=(${finalSize.x.toFixed(4)}, ${finalSize.y.toFixed(4)}, ${finalSize.z.toFixed(4)}) center=(${finalCenter.x.toFixed(4)}, ${finalCenter.y.toFixed(4)}, ${finalCenter.z.toFixed(4)})`);

    // Count meshes for status
    let meshCount = 0;
    root.traverse((obj) => { if (obj.isMesh) meshCount++; });

    this._setStatus(`${meshCount} parts (${unitNote})`);

    // Collect all meshes, make transparent
    this.meshes = [];
    root.traverse((obj) => {
      if (obj.isMesh) {
        // Clone material to avoid mutating shared instances
        obj.material = obj.material.clone();
        const origColor = obj.material.color
          ? obj.material.color.getHex()
          : 0x888888;
        obj.material.transparent = true;
        obj.material.opacity = this.opacity;
        obj.material.depthWrite = this.opacity > 0.9;
        obj.material.side = THREE.DoubleSide;
        this.meshes.push({ mesh: obj, originalColor: origColor });
      }
    });
  }

  // ── Transparency ─────────────────────────────────────────────────

  setOpacity(value) {
    this.opacity = value;
    this.meshes.forEach(({ mesh }) => {
      mesh.material.opacity = value;
      mesh.material.transparent = value < 1.0;
      mesh.material.depthWrite = value > 0.9;
      mesh.material.needsUpdate = true;
    });
  }

  // ── Selection ────────────────────────────────────────────────────

  handleClick(raycaster) {
    if (!this.model || this.meshes.length === 0) return null;

    // Reset previous selection
    if (this.selectedMesh) {
      const prev = this.meshes.find(
        (m) => m.mesh === this.selectedMesh
      );
      if (prev) {
        prev.mesh.material.emissive.setHex(0x000000);
        prev.mesh.material.emissiveIntensity = 0;
      }
    }
    this._removeSelectionBox();

    const targets = this.meshes.map((m) => m.mesh);
    const hits = raycaster.intersectObjects(targets, false);

    if (hits.length === 0) {
      this.selectedMesh = null;
      if (this.onSelect) this.onSelect(null);
      return null;
    }

    const hit = hits[0];
    const mesh = hit.object;
    this.selectedMesh = mesh;

    // Highlight
    mesh.material.emissive.setHex(0xffaa00);
    mesh.material.emissiveIntensity = 0.4;

    // Bounding box
    this._createSelectionBox(mesh);

    // Compute info
    const worldBox = new THREE.Box3().setFromObject(mesh);
    const center = worldBox.getCenter(new THREE.Vector3());
    const bboxSize = worldBox.getSize(new THREE.Vector3());

    // Walk up to find the best name (nearest named parent)
    let name = mesh.name || '';
    if (!name || name.startsWith('mesh') || name.startsWith('Object')) {
      let parent = mesh.parent;
      while (parent && parent !== this.model) {
        if (parent.name && !parent.name.startsWith('Scene')) {
          name = parent.name;
          break;
        }
        parent = parent.parent;
      }
    }
    if (!name) name = '(unnamed)';

    const info = {
      name,
      center,       // THREE.Vector3 in scene meters
      size: bboxSize,
      point: hit.point.clone(),
    };

    if (this.onSelect) this.onSelect(info);
    return info;
  }

  _createSelectionBox(mesh) {
    this.selectionBox = new THREE.BoxHelper(mesh, 0xffaa00);
    this.selectionBox.visible = this.showBBox;
    this.scene.add(this.selectionBox);
  }

  _removeSelectionBox() {
    if (this.selectionBox) {
      this.scene.remove(this.selectionBox);
      this.selectionBox.dispose();
      this.selectionBox = null;
    }
  }

  rotateYaw90() {
    if (!this.model) return;
    this._yawSteps = (this._yawSteps + 1) % 4;
    this._applyOrientation();
    this._removeSelectionBox();
  }

  rotateX90() {
    if (!this.model) return;
    this._xSteps = (this._xSteps + 1) % 4;
    this._applyOrientation();
    this._removeSelectionBox();
  }

  _applyOrientation() {
    if (!this.model) return;
    const xAngle = (this._xSteps * Math.PI) / 2;
    const zAngle = (this._yawSteps * Math.PI) / 2;
    const qX = new THREE.Quaternion();
    qX.setFromAxisAngle(new THREE.Vector3(1, 0, 0), xAngle);
    const qZ = new THREE.Quaternion();
    qZ.setFromAxisAngle(new THREE.Vector3(0, 0, 1), zAngle);
    const combined = new THREE.Quaternion();
    combined.multiplyQuaternions(qZ, qX);
    this.model.quaternion.copy(combined);
    console.log(`[CAD] X=${this._xSteps * 90}° Yaw=${this._yawSteps * 90}°`);
  }

  setShowBBox(show) {
    this.showBBox = show;
    if (this.selectionBox) {
      this.selectionBox.visible = show;
    }
  }

  // ── Cleanup ──────────────────────────────────────────────────────

  unload() {
    this._removeSelectionBox();
    this.selectedMesh = null;

    if (this.model) {
      this.model.traverse((obj) => {
        if (obj.isMesh) {
          obj.geometry.dispose();
          if (obj.material) {
            if (obj.material.map) obj.material.map.dispose();
            obj.material.dispose();
          }
        }
      });
      this.scene.remove(this.model);
      this.model = null;
    }
    this.meshes = [];
  }

  // ── Internal ─────────────────────────────────────────────────────

  _setStatus(text) {
    if (this.onStatusChange) this.onStatusChange(text);
  }
}
